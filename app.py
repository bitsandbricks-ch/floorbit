"""Entry point: ``flask --app app run`` and gunicorn ``app:app``. The app lives in floorbit/."""
from floorbit import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
