from functools import wraps

# Пустой декоратор: пропускает всех без проверки ключа
def shared_key_required(view):
    @wraps(view)
    def _wrap(request, *args, **kwargs):
        return view(request, *args, **kwargs)
    return _wrap

