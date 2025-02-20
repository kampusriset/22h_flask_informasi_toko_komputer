from flask import render_template
from models.database import get_user_data

def user_dashboard():
    user_data = get_user_data()  # Fetch data from the model
    return render_template('user/dashboard.html', data=user_data)  # Pass data to the view 