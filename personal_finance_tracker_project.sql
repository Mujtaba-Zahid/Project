--  PERSONAL FINANCE TRACKER
show data_directory;

-- Tables:

-- users
create table users (
    user_id serial primary key,
    name varchar(100) not null,
    email varchar(150) unique not null,
    phone varchar(20),
    created_at timestamp default current_timestamp
);

-- wallets / accounts
create table accounts (
    account_id serial primary key,
    user_id int references users(user_id),
    account_name varchar(100) not null,
    account_type varchar(20) check (account_type in ('cash','bank','credit','wallet')),
    currency varchar(10) default 'PKR',
    is_active boolean default true,
    created_at timestamp default current_timestamp
);

-- income / expense categories
create table categories (
    category_id serial primary key,
    name varchar(100) not null,
    type varchar(20) check (type in ('income','expense')) not null
);

-- transactions
create table transactions (
    transaction_id serial primary key,
    user_id int references users(user_id),
    account_id int references accounts(account_id),
    category_id int references categories(category_id),
    amount decimal(12,2) check (amount > 0),
    transaction_type varchar(20) check (transaction_type in ('income','expense')),
    description varchar(255),
    transaction_date date not null,
    created_at timestamp default current_timestamp
);

-- account-to-account transfers
create table transfers (
    transfer_id serial primary key,
    user_id int references users(user_id),
    from_account_id int references accounts(account_id),
    to_account_id int references accounts(account_id),
    amount decimal(12,2) check (amount > 0),
    transfer_date date default current_date
);

-- monthly category budgets
create table budgets (
    budget_id serial primary key,
    user_id int references users(user_id),
    category_id int references categories(category_id),
    monthly_limit decimal(12,2) check (monthly_limit > 0),
    month date
);

-- savings goals
create table savings_goals (
    goal_id serial primary key,
    user_id int references users(user_id),
    goal_name varchar(100) not null,
    target_amount decimal(12,2) check (target_amount > 0),
    saved_amount decimal(12,2) default 0 check (saved_amount >= 0),
    deadline date,
    status varchar(20) default 'active' check (status in ('active','completed','cancelled'))
);

-- investments and fixed assets
create table investments (
    investment_id serial primary key,
    user_id int references users(user_id),
    asset_name varchar(100) not null,
    asset_type varchar(30) check (asset_type in ('stock','gold','property','fixed_deposit','crypto','other')),
    purchase_amount decimal(12,2) check (purchase_amount > 0),
    current_value decimal(12,2) check (current_value >= 0),
    purchase_date date not null,
    notes varchar(255)
);

-- recurring / scheduled payments
create table recurring_transactions (
    recurring_id serial primary key,
    user_id int references users(user_id),
    account_id int references accounts(account_id),
    category_id int references categories(category_id),
    amount decimal(12,2) check (amount > 0),
    transaction_type varchar(20) check (transaction_type in ('income','expense')),
    frequency varchar(20) check (frequency in ('daily','weekly','monthly','yearly')),
    next_due_date date not null,
    description varchar(255)
);

-- labels
create table tags (
    tag_id serial primary key,
    name varchar(100) not null
);

create table transaction_tags (
    transaction_id int references transactions(transaction_id),
    tag_id int references tags(tag_id)
);

-- audit log (populated by procedures)
create table audit_log (
    log_id serial primary key,
    table_name varchar(100),
    operation varchar(50),
    record_id int,
    note varchar(255),
    changed_at timestamp default current_timestamp
);

-- csv staging (raw bank statement import)
create table bank_statement_import (
    row_id serial primary key,
    transaction_id varchar(50),
    account_id varchar(50),
    transaction_date varchar(50),
    amount varchar(50),
    transaction_type varchar(50),
    description varchar(255)
);

-- Functions and Procedures:

-- returns live balance for an account
create function get_balance(p_account_id int)
returns decimal as $$
declare
    bal decimal;
begin
    select coalesce(sum(
        case when transaction_type = 'income' then amount else -amount end
    ), 0)
    into bal
    from transactions
    where account_id = p_account_id;
    return bal;
end;
$$ language plpgsql;

-- deposit into account
create procedure deposit_amount(p_account_id int, p_amount decimal)
language plpgsql as $$
declare
    v_user_id int;
begin
    select user_id into v_user_id
    from accounts
    where account_id = p_account_id;

    insert into transactions (user_id, account_id, amount, transaction_type, transaction_date, description)
    values (v_user_id, p_account_id, p_amount, 'income', current_date, 'Manual Deposit');

    insert into audit_log (table_name, operation, record_id, note)
    values ('transactions', 'deposit', p_account_id, 'deposited ' || p_amount);
end;
$$;

-- withdraw with balance check
create procedure withdraw_amount(p_account_id int, p_amount decimal)
language plpgsql as $$
declare
    v_user_id int;
begin
    if get_balance(p_account_id) < p_amount then
        raise exception 'insufficient balance in account %', p_account_id;
    end if;

    select user_id into v_user_id
    from accounts
    where account_id = p_account_id;

    insert into transactions (user_id, account_id, amount, transaction_type, transaction_date, description)
    values (v_user_id, p_account_id, p_amount, 'expense', current_date, 'Manual Withdrawal');

    insert into audit_log (table_name, operation, record_id, note)
    values ('transactions', 'withdrawal', p_account_id, 'withdrew ' || p_amount);
end;
$$;

-- fund transfer with begin / exception
create or replace procedure fund_transfer(p_from int, p_to int, p_amount decimal)
language plpgsql as $$
declare
    v_user_id int;
begin
    if get_balance(p_from) < p_amount then
        raise exception 'insufficient balance for transfer from account %', p_from;
    end if;

    select user_id into v_user_id
    from accounts
    where account_id = p_from;

    insert into transactions (user_id, account_id, amount, transaction_type, transaction_date, description)
    values (v_user_id, p_from, p_amount, 'expense', current_date, 'Transfer Out');

    insert into transactions (user_id, account_id, amount, transaction_type, transaction_date, description)
    values (v_user_id, p_to, p_amount, 'income', current_date, 'Transfer In');

    insert into transfers (user_id, from_account_id, to_account_id, amount, transfer_date)
    values (v_user_id, p_from, p_to, p_amount, current_date);

    insert into audit_log (table_name, operation, record_id, note)
    values ('transfers', 'fund_transfer', p_from, 'transferred ' || p_amount || ' to account ' || p_to);

exception
    when others then
        raise;
end;
$$;

-- savings goal % progress
create or replace function get_goal_progress(p_goal_id int)
returns decimal as $$
declare
    progress decimal;
begin
    select round((saved_amount / target_amount) * 100, 2)
    into progress
    from savings_goals
    where goal_id = p_goal_id;
    return progress;
end;
$$ language plpgsql;

-- mark goal completed if target reached
create or replace procedure update_goal_status(p_goal_id int)
language plpgsql as $$
declare
    v_saved  decimal;
    v_target decimal;
begin
    select saved_amount, target_amount
    into v_saved, v_target
    from savings_goals
    where goal_id = p_goal_id;

    if v_saved >= v_target then
        update savings_goals
        set status = 'completed'
        where goal_id = p_goal_id;
    end if;
end;
$$;


-- Views:

-- live account balance
create view account_balance as
select
    account_id,
    sum(case when transaction_type = 'income' then amount else -amount end) as balance
from transactions
group by account_id;

-- monthly income vs expense
create view monthly_summary as
select
    date_trunc('month', transaction_date) as month,
    sum(case when transaction_type = 'income' then amount else 0 end) as total_income,
    sum(case when transaction_type = 'expense' then amount else 0 end) as total_expense
from transactions
group by 1
order by 1;

-- budget vs actual with remaining
create view budget_vs_actual as
select
    c.name as category,
    b.monthly_limit,
    coalesce(sum(t.amount), 0) as spent,
    (b.monthly_limit - coalesce(sum(t.amount), 0)) as remaining
from budgets b
join categories c on c.category_id = b.category_id
left join transactions t
    on t.category_id = b.category_id
    and t.transaction_type = 'expense'
    and date_trunc('month', t.transaction_date) = date_trunc('month', b.month)
group by c.name, b.monthly_limit;

-- investment portfolio by asset type
create view portfolio_summary as
select
    asset_type,
    count(*) as total_assets,
    sum(purchase_amount) as total_invested,
    sum(current_value) as current_value,
    sum(current_value - purchase_amount) as total_gain_loss
from investments
group by asset_type;

-- net worth per user
create view net_worth as
select
    u.user_id,
    u.name,
    coalesce(ab.total_balance, 0) as wallet_balance,
    coalesce(inv.portfolio_value, 0) as investment_value,
    coalesce(ab.total_balance, 0) + coalesce(inv.portfolio_value, 0) as net_worth
from users u
left join (
    select t.user_id,
           sum(case when t.transaction_type = 'income' then t.amount else -t.amount end) as total_balance
    from transactions t
    group by t.user_id
) ab on ab.user_id = u.user_id
left join (
    select user_id, sum(current_value) as portfolio_value
    from investments
    group by user_id
) inv on inv.user_id = u.user_id;

-- spending breakdown per user per category
create view spending_insights as
select
    t.user_id,
    c.name as category,
    sum(t.amount) as total_spent,
    count(*) as total_transactions,
    round(avg(t.amount), 2) as avg_transaction
from transactions t
join categories c on c.category_id = t.category_id
where t.transaction_type = 'expense'
group by t.user_id, c.name
order by total_spent desc;

-- materialized snapshot of transaction totals
create materialized view mv_transaction_summary as
select
    account_id,
    count(transaction_id) as total_transactions,
    sum(amount) as total_amount
from transactions
group by account_id;

-- refresh when needed
-- refresh materialized view mv_transaction_summary;


-- Indexes:

-- b-tree: range queries on date and amount
create index idx_tx_date on transactions(transaction_date);
create index idx_tx_amount on transactions(amount);

-- hash:- exact match on user and account
create index idx_tx_user_hash on transactions using hash (user_id);
create index idx_tx_account_hash on transactions using hash (account_id);

-- brin:- large sequential date column, low overhead
create index idx_tx_date_brin on transactions using brin (transaction_date);

-- composite: common filter pattern
create index idx_tx_category on transactions(category_id, transaction_type);


-- Sample Data:

insert into users (name, email, phone) values
('Nofil', 'nofil@email.com', '0312-1234567'),
('Sara', 'sara@email.com', '0333-9876543');

insert into accounts (user_id, account_name, account_type) values
(1, 'Cash Wallet', 'cash'),
(1, 'Bank Account', 'bank'),
(2, 'Sara Wallet', 'wallet'),
(2, 'Sara Bank', 'bank');

insert into categories (name, type) values
('Salary', 'income'),
('Freelance', 'income'),
('Food', 'expense'),
('Transport', 'expense'),
('Utilities', 'expense'),
('Entertainment', 'expense'),
('Health', 'expense'),
('Rent', 'expense');

insert into tags (name) values
('essential'),
('leisure'),
('recurring'),
('one-time');

insert into transactions (user_id, account_id, category_id, amount, transaction_type, transaction_date, description) values
(1, 2, 1, 120000, 'income',  '2026-05-01', 'May Salary'),
(1, 2, 2, 25000, 'income',  '2026-05-03', 'Freelance Project'),
(1, 1, 3, 3500, 'expense', '2026-05-04', 'Groceries'),
(1, 1, 3, 1200, 'expense', '2026-05-06', 'Lunch'),
(1, 1, 4, 800, 'expense', '2026-05-07', 'Fuel'),
(1, 1, 5, 5000, 'expense', '2026-05-08', 'Electricity Bill'),
(1, 1, 6, 2000, 'expense', '2026-05-09', 'Netflix + Spotify'),
(1, 1, 8, 35000, 'expense', '2026-05-10', 'May Rent'),
(2, 4, 1, 80000, 'income',  '2026-05-01', 'May Salary'),
(2, 3, 3, 2200, 'expense', '2026-05-05', 'Grocery Run'),
(2, 3, 7, 4500, 'expense', '2026-05-07', 'Doctor Visit'),
(2, 3, 4, 600, 'expense', '2026-05-09', 'Uber');

insert into transaction_tags (transaction_id, tag_id) values
(3, 1), (4, 1), (5, 1),
(6, 3), (7, 2), (8, 3);

insert into budgets (user_id, category_id, monthly_limit, month) values
(1, 3, 8000,  '2026-05-01'),
(1, 5, 6000,  '2026-05-01'),
(1, 6, 3000,  '2026-05-01'),
(1, 8, 40000, '2026-05-01'),
(2, 3, 5000,  '2026-05-01'),
(2, 7, 5000,  '2026-05-01');

insert into savings_goals (user_id, goal_name, target_amount, saved_amount, deadline) values
(1, 'Emergency Fund', 200000, 45000, '2026-12-31'),
(1, 'Laptop Upgrade',  80000, 20000, '2026-08-01'),
(2, 'Vacation Fund',   60000, 12000, '2026-10-01');

insert into investments (user_id, asset_name, asset_type, purchase_amount, current_value, purchase_date, notes) values
(1, 'Gold 10g',       'gold',          85000,  92000,  '2025-11-01', '10 gram 24k'),
(1, 'PTCL Shares',    'stock',         30000,  27500,  '2025-09-15', '500 shares'),
(1, 'Meezan FD',      'fixed_deposit', 100000, 109000, '2025-06-01', '1 year FD at 9%'),
(2, 'Prize Bond 40k', 'other',         40000,  40000,  '2025-01-01', 'national prize bond'),
(2, 'DHA Plot Token', 'property',      500000, 550000, '2024-06-01', 'E-block token');

insert into recurring_transactions (user_id, account_id, category_id, amount, transaction_type, frequency, next_due_date, description) values
(1, 1, 5, 5000,  'expense', 'monthly', '2026-06-08', 'Electricity Bill'),
(1, 1, 8, 35000, 'expense', 'monthly', '2026-06-10', 'Monthly Rent'),
(1, 1, 6, 1100,  'expense', 'monthly', '2026-06-01', 'Netflix'),
(2, 3, 4, 3000,  'expense', 'monthly', '2026-06-05', 'Petrol Budget');


-- Transaction Control

call deposit_amount(2, 10000);
call withdraw_amount(1, 2000);
call fund_transfer(2, 1, 5000);

-- intentional fail: no balance
-- call withdraw_amount(3, 999999);



-- CSV import and data cleaning:

copy bank_statement_import(transaction_id, account_id, transaction_date, amount, transaction_type, description)
from 'C:/Program Files/PostgreSQL/17/data/bank_statement.csv'
delimiter ','
csv header;

select * from bank_statement_import;

-- standardize casing
update bank_statement_import
set transaction_type = upper(transaction_type);

-- fix negative amounts using abs logic
update bank_statement_import
set amount = replace(amount, '-', '')
where amount like '-%';

-- remove rows with missing date or amount
delete from bank_statement_import
where transaction_date is null or transaction_date = ''
   or amount is null or amount = '';

-- remove duplicates, keep lowest row_id
delete from bank_statement_import
where row_id not in (
    select min(row_id)
    from bank_statement_import
    group by account_id, transaction_date, amount
);

-- export monthly summary report
copy (
    select
        transaction_date,
        transaction_type,
        count(*) as total_transactions,
        sum(amount::decimal) as total_amount
    from bank_statement_import
    group by 1, 2
    order by 1
)
to 'C:/Program Files/PostgreSQL/17/data/monthly_summary_report.csv'
delimiter ','
csv header;

-- export cleaned data
copy bank_statement_import
to 'C:/Program Files/PostgreSQL/17/data/cleaned_bank_statement.csv'
delimiter ','
csv header;


-- Data ANalytics Queries:

select * from account_balance;
select * from monthly_summary;
select * from budget_vs_actual;
select * from net_worth;
select * from portfolio_summary;
select * from spending_insights;
select * from audit_log order by changed_at desc;

-- full transaction history with joins
select
    t.transaction_id,
    u.name,
    a.account_name,
    c.name as category,
    t.amount,
    t.transaction_type,
    t.transaction_date,
    t.description
from transactions t
join users u on u.user_id = t.user_id
join accounts a on a.account_id = t.account_id
left join categories c on c.category_id = t.category_id
order by t.transaction_date desc;

-- top spending categories
select c.name, sum(t.amount) as total_spent
from transactions t
join categories c on c.category_id = t.category_id
where t.transaction_type = 'expense'
group by c.name
order by total_spent desc;

-- daily expense trend
select transaction_date, sum(amount) as daily_expense
from transactions
where transaction_type = 'expense'
group by transaction_date
order by transaction_date;

-- recurring payments due this month
select description, amount, frequency, next_due_date
from recurring_transactions
where date_trunc('month', next_due_date) = date_trunc('month', current_date);

-- savings goal progress
select goal_name, target_amount, saved_amount, get_goal_progress(goal_id) as progress_pct
from savings_goals;

-- investment gain / loss
select asset_name, asset_type, purchase_amount, current_value,
       (current_value - purchase_amount) as gain_loss
from investments
order by gain_loss desc;


-- Subqueries:

-- transactions above overall average expense
select user_id, amount, transaction_date
from transactions
where transaction_type = 'expense'
  and amount > (
      select avg(amount)
      from transactions
      where transaction_type = 'expense'
  );

-- accounts with no activity this month
select account_id, account_name
from accounts
where account_id not in (
    select distinct account_id
    from transactions
    where date_trunc('month', transaction_date) = date_trunc('month', current_date)
);

-- highest expense per category
select category_id, amount, transaction_date, description
from transactions t
where transaction_type = 'expense'
  and amount = (
      select max(amount)
      from transactions
      where category_id = t.category_id
        and transaction_type = 'expense'
  );

-- categories over budget this month
select category_id, sum(amount) as spent
from transactions
where transaction_type = 'expense'
  and date_trunc('month', transaction_date) = date_trunc('month', current_date)
group by category_id
having sum(amount) > (
    select monthly_limit
    from budgets
    where category_id = transactions.category_id
      and date_trunc('month', month) = date_trunc('month', current_date)
    limit 1
);

-- investments currently above average purchase value
select asset_name, asset_type, current_value,
       (current_value - purchase_amount) as gain
from investments
where current_value > (
    select avg(purchase_amount) from investments
);


-- Indexing Performance

-- bulk insert for testing
insert into transactions (user_id, account_id, category_id, amount, transaction_type, transaction_date, description)
select
    (random() * 2 + 1)::int,
    (random() * 4 + 1)::int,
    (random() * 8 + 1)::int,
    round((random() * 50000)::decimal, 2),
    case when random() > 0.5 then 'income' else 'expense' end,
    current_date - (random() * 365)::int,
    md5(random()::text)
from generate_series(1, 5000);

-- before indexes
explain analyze select * from transactions where transaction_date = '2026-05-01';
explain analyze select * from transactions where user_id = 1;
explain analyze select * from transactions where amount > 40000;

-- indexes already created above:
-- b-tree  : idx_tx_date, idx_tx_amount
-- hash    : idx_tx_user_hash, idx_tx_account_hash
-- brin    : idx_tx_date_brin
-- composite: idx_tx_category

-- after indexes
explain analyze select * from transactions where transaction_date = '2026-05-01';
explain analyze select * from transactions where user_id = 1;
explain analyze select * from transactions where amount > 40000;


-- normalization reference

-- unnormalized (UNF) — one flat table:
-- account_id | customer_name | branch_name | transactions
-- 101        | Ali           | Karachi     | 5000, 2000
--
-- 1NF — atomic values, one row per transaction:
-- account_id | customer_name | branch_name | amount
-- 101        | Ali           | Karachi     | 5000
-- 101        | Ali           | Karachi     | 2000
--
-- 2NF — remove partial dependency (customer split from transactions):
-- accounts(account_id, customer_name, branch_name)
-- transactions(transaction_id, account_id, amount)
--
-- 3NF — remove transitive dependency (branch split out):
-- accounts(account_id, user_id)
-- users(user_id, name)
-- categories(category_id, name, type)
-- transactions(transaction_id, account_id, category_id, amount)
--
-- current schema is in 3NF