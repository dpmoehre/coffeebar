"""业务冲突。路由层转成 409。"""


class Conflict(Exception):
    """业务上不该继续的情况，路由层转成 409。"""

    def __init__(self, message: str, extra: dict | None = None):
        super().__init__(message)
        self.extra = extra or {}
