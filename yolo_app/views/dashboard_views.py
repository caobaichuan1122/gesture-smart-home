from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods


def login_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        return render(request, 'login.html', {'error': 'Invalid username or password'})
    return render(request, 'login.html')


@login_required(login_url='/')
def dashboard_page(request):
    return render(request, 'dashboard.html')


@login_required(login_url='/')
def gesture_logs_page(request):
    return render(request, 'gesture_logs.html')


def logout_view(request):
    logout(request)
    return redirect('login')
