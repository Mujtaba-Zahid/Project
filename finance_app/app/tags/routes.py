from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from . import tags_bp
from ..extensions import db
from ..models.tag import Tag


@tags_bp.route('/')
@login_required
def index():
    tags = Tag.query.filter(
        db.or_(Tag.user_id == current_user.user_id, Tag.user_id.is_(None))
    ).all()
    return render_template('tags/list.html', tags=tags)


@tags_bp.route('/add', methods=['POST'])
@login_required
def add():
    name = request.form.get('name', '').strip()
    color = request.form.get('color', '#6366f1')
    if not name:
        flash('Tag name is required.', 'danger')
        return redirect(url_for('tags.index'))

    tag = Tag(user_id=current_user.user_id, name=name, color=color)
    db.session.add(tag)
    db.session.commit()
    flash('Tag created!', 'success')
    return redirect(url_for('tags.index'))


@tags_bp.route('/edit/<int:tag_id>', methods=['POST'])
@login_required
def edit(tag_id):
    tag = Tag.query.filter_by(tag_id=tag_id, user_id=current_user.user_id).first_or_404()
    tag.name = request.form.get('name', tag.name).strip()
    tag.color = request.form.get('color', tag.color)
    db.session.commit()
    flash('Tag updated!', 'success')
    return redirect(url_for('tags.index'))


@tags_bp.route('/delete/<int:tag_id>', methods=['POST'])
@login_required
def delete(tag_id):
    tag = Tag.query.filter_by(tag_id=tag_id, user_id=current_user.user_id).first_or_404()
    db.session.delete(tag)
    db.session.commit()
    flash('Tag deleted.', 'info')
    return redirect(url_for('tags.index'))
