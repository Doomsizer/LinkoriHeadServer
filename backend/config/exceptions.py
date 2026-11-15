from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, dict) and "detail" not in data:
        first_message = "Ошибка валидации запроса"
        for field, errors in data.items():
            if isinstance(errors, list) and errors:
                first_message = f"{field}: {errors[0]}"
                break
            if isinstance(errors, str):
                first_message = f"{field}: {errors}"
                break
        response.data = {"detail": first_message, "errors": data}
    elif isinstance(data, list) and data:
        response.data = {"detail": str(data[0])}

    return response