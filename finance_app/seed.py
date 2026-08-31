"""Seed script — creates default system categories and sample data."""
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.category import Category
from app.models.tag import Tag


def seed():
    app = create_app()
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()

        # Check if already seeded
        if User.query.first():
            print('Database already has data. Skipping seed.')
            return

        # Create demo user
        demo = User(
            name='Nofil',
            email='nofil@email.com',
            phone='0312-1234567',
        )
        demo.set_password('password123')
        db.session.add(demo)
        db.session.flush()

        # Default categories
        categories = [
            ('Salary', 'income', '💰'),
            ('Freelance', 'income', '💻'),
            ('Food', 'expense', '🍔'),
            ('Transport', 'expense', '🚗'),
            ('Utilities', 'expense', '💡'),
            ('Entertainment', 'expense', '🎬'),
            ('Health', 'expense', '🏥'),
            ('Rent', 'expense', '🏠'),
            ('Shopping', 'expense', '🛍️'),
            ('Education', 'expense', '📚'),
        ]
        for name, cat_type, icon in categories:
            cat = Category(user_id=demo.user_id, name=name, type=cat_type, icon=icon, is_default=True)
            db.session.add(cat)

        # Default tags
        tags = [
            ('essential', '#10b981'),
            ('leisure', '#f59e0b'),
            ('recurring', '#6366f1'),
            ('one-time', '#22d3ee'),
        ]
        for name, color in tags:
            tag = Tag(user_id=demo.user_id, name=name, color=color)
            db.session.add(tag)

        db.session.commit()
        print(f'Seeded demo user: nofil@email.com / password123')
        print(f'Created {len(categories)} categories and {len(tags)} tags.')


if __name__ == '__main__':
    seed()
