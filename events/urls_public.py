from rest_framework.routers import SimpleRouter

from .views import PublicEventViewSet

router = SimpleRouter()
router.register("events", PublicEventViewSet, basename="public-events")

urlpatterns = router.urls
