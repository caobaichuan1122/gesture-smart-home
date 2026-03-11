from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import (
    TokenObtainPairView, TokenRefreshView, TokenVerifyView,
)
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from yolo_app.auth_views import RegisterView
from yolo_app.views.dashboard_views import (
    login_page, dashboard_page, logout_view, gesture_logs_page,
)
from yolo_app.views.camera_api import camera_view, camera_stream, camera_snapshot

urlpatterns = [
    path('admin/', admin.site.urls),

    # ── OpenAPI schema + docs ─────────────────────────────────────────────────
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # ── JWT auth endpoints ────────────────────────────────────────────────────
    path('api/v1/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('api/v1/auth/register/', RegisterView.as_view(), name='register'),

    # ── Business API v1 ───────────────────────────────────────────────────────
    path('api/v1/', include('yolo_app.urls')),

    # ── Camera browser page + MJPEG stream (session auth via @login_required) ─
    path('cameras/<int:camera_id>/', camera_view, name='camera_view'),

    # ── Frontend Dashboard (session-based) ────────────────────────────────────
    path('', login_page, name='login'),
    path('dashboard/', dashboard_page, name='dashboard'),
    path('dashboard/logs/', gesture_logs_page, name='gesture_logs'),
    path('logout/', logout_view, name='logout'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
