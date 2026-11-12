from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """``?page=1&page_size=50`` (max 200) → ``{count, next, previous, results}`` (CONTRATS §2)."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
