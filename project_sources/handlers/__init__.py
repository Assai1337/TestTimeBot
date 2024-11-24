from .main_menu import router as main_menu_router
from .test_passing import router as test_passing_router
from .results_view import router as results_view_router


def register_handlers(dp):
    dp.include_router(main_menu_router)
    dp.include_router(test_passing_router)
    dp.include_router(results_view_router)
