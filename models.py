from config import db

# Modelo de usuario en SQLAlchemy
class User(db.Model):
    __tablename__ = 'Users'
    __table_args__ = {'schema': 'dbo'}
    
    Id = db.Column(db.Integer, primary_key=True)
    Nombre = db.Column(db.String(100), nullable=False)
    Correo = db.Column(db.String(100), unique=True, nullable=False)
    Rol = db.Column(db.String(50), nullable=False)

