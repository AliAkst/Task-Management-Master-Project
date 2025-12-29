class TaskNotFoundException(Exception):
    """Bir Görev veritabanında bulunamadığında Fırlatılır"""

    def __init__(self, task_id: int):
        self.task_id = task_id

        self.message = f"Task with id {task_id} not found"

        super().__init__(self.message)


class TaskBadRequestException(Exception):
    """Hatalı bir istek gönderildiğinde fırlatılır"""

    def __init__(self, message: str):
        super().__init__(message)
