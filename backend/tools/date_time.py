from datetime import datetime


def get_current_datetime():
    current = datetime.now().astimezone()
    return {
        'iso': current.isoformat(timespec='seconds'),
        'timezone': current.tzname() or 'local time',
    }
