"""Attach native MP administration checks to this plugin's HTTP endpoints."""
from __future__ import annotations

import functools
import inspect


def unavailable_administration():
    from fastapi import HTTPException
    raise HTTPException(status_code=503, detail="宿主管理权限契约不可用，本插件管理操作已暂停")


def protect_endpoint(endpoint):
    """Preserve body/query binding while letting FastAPI run MP's dependency."""
    try:
        from fastapi import Depends
        try:
            from app.api.dependencies.auth import get_current_active_superuser as permission
        except ImportError:
            from app.api.endpoints.user import get_current_active_superuser as permission
    except ImportError:
        try:
            from fastapi import Depends
        except ImportError:
            # A real MP installation provides FastAPI. Synthetic non-HTTP tests
            # call orchestration methods directly and do not expose routes.
            return endpoint
        permission = unavailable_administration
    signature = inspect.signature(endpoint)
    parameters = list(signature.parameters.values())
    parameters.append(inspect.Parameter("_doc115_principal", inspect.Parameter.KEYWORD_ONLY,
                                        default=Depends(permission)))

    @functools.wraps(endpoint)
    def authorized(*args, **kwargs):
        kwargs.pop("_doc115_principal", None)
        return endpoint(*args, **kwargs)

    authorized.__signature__ = signature.replace(parameters=parameters)
    authorized.__doc115_permission__ = permission
    return authorized
