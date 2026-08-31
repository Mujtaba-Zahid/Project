from ..extensions import db


class Tag(db.Model):
    """User-specific label/tag with color for UI."""
    __tablename__ = 'tags'

    tag_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), default='#6366f1')

    def __repr__(self):
        return f'<Tag {self.tag_id}: {self.name}>'
