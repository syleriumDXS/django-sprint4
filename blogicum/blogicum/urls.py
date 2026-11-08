"""Root routes, authentication and development media serving."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from blog.views import ConfirmLogoutView, RegistrationView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/registration/',
         RegistrationView.as_view(), name='registration'),
    path('auth/logout/', ConfirmLogoutView.as_view(), name='logout'),
    path('auth/', include('django.contrib.auth.urls')),
    path('pages/', include('pages.urls')),
    path('', include('blog.urls')),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL, document_root=settings.MEDIA_ROOT,
    )

handler404 = 'pages.views.page_not_found'
handler500 = 'pages.views.server_error'
