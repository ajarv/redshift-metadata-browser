from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"entities", views.EntityViewSet, basename="entity")

urlpatterns = [
    path("schemas/", views.schema_list, name="schema-list"),
    path("schemas/<str:schema_name>/children/", views.schema_children, name="schema-children"),
    path("search/", views.search_entities, name="search"),
    path("tasks/", views.task_list, name="task-list"),
    path("tasks/<uuid:task_id>/", views.task_detail, name="task-detail"),
    path("", include(router.urls)),
]
