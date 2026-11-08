"""Publication lists, author tools and comments."""
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LogoutView
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods
from django.views.generic import CreateView

from .forms import CommentForm, PostForm, ProfileForm
from .models import Category, Comment, Post

POSTS_PER_PAGE = 10
User = get_user_model()


def posts_with_related():
    return Post.objects.select_related('author', 'category', 'location')


def public_filter():
    return Q(is_published=True, category__is_published=True,
             pub_date__lte=timezone.now())


def published_posts():
    return posts_with_related().filter(public_filter())


def visible_post(request, post_id):
    visibility = public_filter()
    if request.user.is_authenticated:
        visibility |= Q(author=request.user)
    posts = posts_with_related().filter(visibility)
    return get_object_or_404(posts, pk=post_id)


def paginate(request, posts):
    posts = posts.annotate(comment_count=Count('comments')).order_by(
        '-pub_date', '-pk',
    )
    return Paginator(posts, POSTS_PER_PAGE).get_page(request.GET.get('page'))


@require_GET
def index(request):
    return render(request, 'blog/index.html', {
        'page_obj': paginate(request, published_posts()),
    })


@require_GET
def category_posts(request, category_slug):
    category = get_object_or_404(
        Category, slug=category_slug, is_published=True,
    )
    posts = published_posts().filter(category=category)
    return render(request, 'blog/category.html', {
        'category': category,
        'page_obj': paginate(request, posts),
    })


@require_GET
def profile(request, username):
    owner = get_object_or_404(User, username=username)
    posts = posts_with_related().filter(author=owner)
    if request.user != owner:
        posts = posts.filter(public_filter())
    return render(request, 'blog/profile.html', {
        'profile': owner, 'page_obj': paginate(request, posts),
    })


@require_GET
def post_detail(request, post_id):
    post = visible_post(request, post_id)
    return render(request, 'blog/detail.html', {
        'post': post, 'form': CommentForm(),
        'comments': post.comments.select_related('author'),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def create_post(request):
    form = PostForm(
        request.POST if request.method == 'POST' else None,
        request.FILES or None,
    )
    if request.method == 'POST' and form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        post.save()
        return redirect('blog:profile', username=request.user.username)
    return render(request, 'blog/create.html', {'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
def edit_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if post.author != request.user:
        return redirect('blog:post_detail', post_id=post.pk)
    form = PostForm(
        request.POST if request.method == 'POST' else None,
        request.FILES or None, instance=post,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('blog:post_detail', post_id=post.pk)
    return render(request, 'blog/create.html', {'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
def delete_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if post.author != request.user:
        return redirect('blog:post_detail', post_id=post.pk)
    if request.method == 'POST':
        post.delete()
        return redirect('blog:profile', username=request.user.username)
    return render(request, 'blog/create.html', {
        'form': PostForm(instance=post),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def edit_profile(request):
    form = ProfileForm(
        request.POST if request.method == 'POST' else None,
        instance=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        return redirect('blog:profile', username=user.username)
    return render(request, 'blog/user.html', {'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
def add_comment(request, post_id):
    post = visible_post(request, post_id)
    if request.method == 'GET':
        return redirect('blog:post_detail', post_id=post.pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.post = post
        comment.author = request.user
        comment.save()
        return redirect('blog:post_detail', post_id=post.pk)
    return render(request, 'blog/detail.html', {
        'post': post, 'form': form,
        'comments': post.comments.select_related('author'),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def edit_comment(request, post_id, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id, post_id=post_id)
    if comment.author != request.user:
        return redirect('blog:post_detail', post_id=post_id)
    form = CommentForm(
        request.POST if request.method == 'POST' else None, instance=comment,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('blog:post_detail', post_id=post_id)
    return render(request, 'blog/comment.html', {
        'form': form, 'comment': comment,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def delete_comment(request, post_id, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id, post_id=post_id)
    if comment.author != request.user:
        return redirect('blog:post_detail', post_id=post_id)
    if request.method == 'POST':
        comment.delete()
        return redirect('blog:post_detail', post_id=post_id)
    return render(request, 'blog/comment.html', {'comment': comment})


class RegistrationView(CreateView):
    form_class = UserCreationForm
    template_name = 'registration/registration_form.html'
    success_url = reverse_lazy('login')


class ConfirmLogoutView(LogoutView):
    """Confirm the GET link and perform logout via CSRF-protected POST."""

    http_method_names = ['get', 'post', 'options']

    def get(self, request, *args, **kwargs):
        return render(request, 'registration/logout_confirm.html')
