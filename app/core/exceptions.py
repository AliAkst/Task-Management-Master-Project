class AppException(Exception):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
    ):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        super().__init__(self.message)


class TaskNotFoundException(AppException):
    def __init__(self, task_id: int):
        super().__init__(
            status_code=404,
            error_code="TASK_NOT_FOUND",
            message=f"Task with id {task_id} not found",
        )


class TaskBadRequestException(AppException):
    def __init__(self, message: str):
        super().__init__(
            status_code=400, error_code="TASK_BAD_REQUEST", message=message
        )


class ValidationException(AppException):
    def __init__(self, message: str):
        super().__init__(
            status_code=422, error_code="VALIDATION_ERROR", message=message
        )
