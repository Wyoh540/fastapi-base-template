"""FastAPI reference application package.

Modules are organised by bounded context (``auth``, ``posts``) rather than by
file type. Cross-domain imports must always name the module explicitly, e.g.::

    from src.auth import service as auth_service
    from src.posts.constants import ErrorCode as PostsErrorCode
"""
