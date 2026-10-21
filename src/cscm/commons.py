"""
CSCM Common Utilities & Decorators.
"""

from functools import wraps
from threading import Lock
from typing import Any, Callable, Dict, Type, TypeVar

T = TypeVar("T")


def singleton(cls: Type[T]) -> Callable[..., T]:
    """
    Thread-safe class decorator for ensuring a single instance of a class.
    
    Provides a `.reset_instance()` method on the wrapped class to allow
    clean isolation during unit testing.
    
    Usage:
        @singleton
        class MyService:
            ...
            
        instance = MyService()
        MyService.reset_instance()  # in tests
    """
    instances: Dict[Type[T], T] = {}
    lock = Lock()

    @wraps(cls)
    def get_instance(*args: Any, **kwargs: Any) -> T:
        # If explicit arguments/overrides are provided, instantiate an isolated instance
        if args or kwargs:
            return cls(*args, **kwargs)

        if cls not in instances:
            with lock:
                if cls not in instances:
                    instances[cls] = cls()
        return instances[cls]

    def reset_instance() -> None:
        """Reset the cached singleton instance (primarily for test isolation)."""
        with lock:
            instances.pop(cls, None)

    get_instance.reset_instance = reset_instance  # type: ignore[attr-defined]
    get_instance.__wrapped_cls__ = cls  # type: ignore[attr-defined]
    return get_instance


def is_singleton(target: Any) -> bool:
    """Check whether a target class or callable was decorated with @singleton."""
    return hasattr(target, "reset_instance") and hasattr(target, "__wrapped_cls__")