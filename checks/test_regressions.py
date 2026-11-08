"""Additional checks for permissions, uploads, auth and email delivery."""
from datetime import timedelta
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from blog.models import Category, Comment, Post

pytestmark = pytest.mark.django_db


@pytest.fixture
def sample(client):
    user_model = get_user_model()
    owner = user_model.objects.create_user('owner', 'owner@example.com',
                                          'Strong-password-123')
    stranger = user_model.objects.create_user('stranger')
    category = Category.objects.create(title='Test', slug='test')
    post = Post.objects.create(
        title='Public post', text='Body', author=owner, category=category,
        pub_date=timezone.now() - timedelta(days=1),
    )
    return owner, stranger, category, post


@pytest.mark.parametrize('kind', ['future', 'unpublished', 'hidden_category'])
def test_private_visibility_and_comment_access(client, sample, kind):
    owner, stranger, category, post = sample
    if kind == 'future':
        post.pub_date = timezone.now() + timedelta(days=1)
    elif kind == 'unpublished':
        post.is_published = False
    else:
        category.is_published = False
        category.save()
    post.save()
    for viewer in (None, stranger, owner):
        client.logout()
        if viewer:
            client.force_login(viewer)
        is_owner = viewer == owner
        response = client.get(f'/posts/{post.pk}/')
        assert response.status_code == (200 if is_owner else 404)
        profile = client.get('/profile/owner/')
        assert len(profile.context['page_obj']) == (1 if is_owner else 0)
        if viewer:
            response = client.post(f'/posts/{post.pk}/comment/', {'text': 'x'})
            assert response.status_code == (302 if is_owner else 404)


@pytest.mark.parametrize('action', ['edit', 'delete'])
def test_foreign_post_cannot_change(client, sample, action):
    owner, stranger, category, post = sample
    client.force_login(stranger)
    response = client.post(f'/posts/{post.pk}/{action}/', {'title': 'Hacked'})
    assert response.status_code == 302
    assert response.url == f'/posts/{post.pk}/'
    post.refresh_from_db()
    assert post.title == 'Public post'


@pytest.mark.parametrize('action', ['edit_comment', 'delete_comment'])
def test_comment_ownership_and_nested_id(client, sample, action):
    owner, stranger, category, post = sample
    comment = Comment.objects.create(post=post, author=owner, text='Original')
    client.force_login(stranger)
    url = f'/posts/{post.pk}/{action}/{comment.pk}/'
    assert client.post(url, {'text': 'Hacked'}).status_code == 302
    comment.refresh_from_db()
    assert comment.text == 'Original'
    client.force_login(owner)
    wrong_url = f'/posts/{post.pk + 1}/{action}/{comment.pk}/'
    assert client.post(wrong_url, {'text': 'Hacked'}).status_code == 404
    comment.refresh_from_db()
    assert comment.text == 'Original'


def test_get_deletion_is_only_confirmation(client, sample):
    owner, stranger, category, post = sample
    comment = Comment.objects.create(post=post, author=owner, text='To delete')
    client.force_login(owner)
    assert client.get(f'/posts/{post.pk}/delete/').status_code == 200
    assert client.get(
        f'/posts/{post.pk}/delete_comment/{comment.pk}/'
    ).status_code == 200
    assert Post.objects.filter(pk=post.pk).exists()
    assert Comment.objects.filter(pk=comment.pk).exists()
    assert client.post(f'/posts/{post.pk}/delete/').status_code == 302
    assert not Comment.objects.filter(pk=comment.pk).exists()


def test_upload_and_no_author_spoofing(client, sample, settings, tmp_path):
    owner, stranger, category, post = sample
    settings.MEDIA_ROOT = tmp_path
    client.force_login(owner)
    image_bytes = BytesIO()
    Image.new('RGB', (3, 3)).save(image_bytes, format='PNG')
    data = {
        'title': 'With image', 'text': 'Image body',
        'pub_date': '2020-01-01T12:00', 'category': category.pk,
        'author': stranger.pk, 'is_published': False,
        'image': SimpleUploadedFile('picture.png', image_bytes.getvalue(),
                                   content_type='image/png'),
    }
    response = client.post('/posts/create/', data)
    assert response.status_code == 302
    created = Post.objects.get(title='With image')
    assert created.author == owner
    assert created.is_published
    assert (tmp_path / created.image.name).exists()
    for url in ('/', '/profile/owner/', '/category/test/',
                f'/posts/{created.pk}/'):
        assert created.image.url in client.get(url).content.decode()


def test_invalid_image_rejected(client, sample):
    owner, stranger, category, post = sample
    client.force_login(owner)
    response = client.post('/posts/create/', {
        'title': 'Invalid image', 'text': 'Body',
        'pub_date': '2020-01-01T12:00', 'category': category.pk,
        'image': SimpleUploadedFile('image.png', b'not an image'),
    })
    assert response.status_code == 200
    assert 'image' in response.context['form'].errors
    assert not Post.objects.filter(title='Invalid image').exists()


def test_profile_no_privilege_escalation(client, sample):
    owner, stranger, category, post = sample
    client.force_login(owner)
    response = client.post('/edit_profile/', {
        'username': 'renamed', 'first_name': 'Name', 'last_name': 'Surname',
        'email': 'new@example.com', 'is_staff': True, 'is_superuser': True,
    })
    assert response.url == '/profile/renamed/'
    owner.refresh_from_db()
    assert not owner.is_staff and not owner.is_superuser
    assert owner.email == 'new@example.com'


def test_password_reset_writes_file(client, sample, settings, tmp_path):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
    settings.EMAIL_FILE_PATH = tmp_path
    response = client.post(reverse('password_reset'), {
        'email': 'owner@example.com',
    })
    assert response.status_code == 302
    messages = list(tmp_path.iterdir())
    assert len(messages) == 1
    assert '/auth/reset/' in messages[0].read_text()


def test_csrf_and_logout_confirmation(sample):
    owner, stranger, category, post = sample
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    assert client.post(f'/posts/{post.pk}/delete/').status_code == 403
    response = client.get('/auth/logout/')
    assert response.status_code == 200
    assert client.session.get('_auth_user_id') == str(owner.pk)
    assert client.post('/auth/logout/').status_code == 403
    token = client.cookies['csrftoken'].value
    assert client.post('/auth/logout/', {
        'csrfmiddlewaretoken': token,
    }).status_code == 200
    assert '_auth_user_id' not in client.session


def test_registration_and_login(client):
    response = client.post('/auth/registration/', {
        'username': 'new_user', 'password1': 'Strong-password-123',
        'password2': 'Strong-password-123',
    })
    assert response.status_code == 302
    assert client.login(username='new_user', password='Strong-password-123')


def test_empty_create_form_has_errors(client, sample):
    client.force_login(sample[0])
    response = client.post('/posts/create/', {})
    assert response.context['form'].errors
