"""Lightweight smoke tests for blog behavior (run with pytest-django)."""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from blog.models import Category, Location, Post

pytestmark = pytest.mark.django_db


@pytest.fixture
def category():
    return Category.objects.create(
        title='Путешествия', description='О поездках', slug='travel')


@pytest.fixture
def author():
    return get_user_model().objects.create_user(username='test_author')


def new_post(category, author, **kwargs):
    data = {
        'title': 'Проверочная запись', 'text': 'Проверочный текст',
        'pub_date': timezone.now() - timedelta(days=1),
        'category': category, 'author': author,
    }
    data.update(kwargs)
    return Post.objects.create(**data)


def test_home_shows_only_ten_latest_posts(client, category, author):
    for i in range(12):
        new_post(category, author, title=f'Пост {i}',
                 pub_date=timezone.now() - timedelta(days=12-i))
    response = client.get(reverse('blog:index'))
    assert response.status_code == 200
    assert len(response.context['page_obj'].object_list) == 10
    assert response.context['page_obj'].object_list[0].title == 'Пост 11'


def test_unpublished_and_future_posts_hidden(client, category, author):
    new_post(category, author, is_published=False)
    new_post(category, author, pub_date=timezone.now() + timedelta(days=1))
    response = client.get('/')
    assert len(response.context['page_obj'].object_list) == 0


def test_hidden_category_hides_post(client, category, author):
    post = new_post(category, author)
    category.is_published = False
    category.save()
    assert client.get(f'/posts/{post.pk}/').status_code == 404
    assert client.get('/category/travel/').status_code == 404
    assert len(client.get('/').context['page_obj'].object_list) == 0


def test_unpublished_location_does_not_hide_post(client, category, author):
    location = Location.objects.create(name='Локация', is_published=False)
    post = new_post(category, author, location=location)
    response = client.get(f'/posts/{post.pk}/')
    assert response.status_code == 200
    assert 'Планета Земля' in response.content.decode()
    assert len(client.get('/').context['page_obj'].object_list) == 1


def test_category_lists_only_its_posts(client, category, author):
    new_post(category, author)
    other = Category.objects.create(title='Другое', description='x',
                                    slug='other')
    new_post(other, author)
    response = client.get('/category/travel/')
    assert len(response.context['page_obj'].object_list) == 1
    assert response.context['category'] == category


def test_foreign_key_delete(client, category, author):
    loc = Location.objects.create(name='Москва')
    post = new_post(category, author, location=loc)
    loc.delete()
    post.refresh_from_db()
    assert post.location is None
    category.delete()
    post.refresh_from_db()
    assert post.category is None
    assert client.get(f'/posts/{post.pk}/').status_code == 404
