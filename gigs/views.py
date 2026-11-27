import datetime
import functools
import json
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages 

# Local App Imports
from gigs.models import (
    Musician, 
    Band, 
    Listing, 
    Application, 
    Review, 
    MediaLink, 
    BandInterest
)
from gigs.forms import (
    UserSignUpForm, MusicianProfileForm, BandProfileForm,
    AccountEditForm, MusicianEditForm, BandEditForm,
)
from gigs.reviews import ReviewForm, gig_review_problem, musician_review_problem

# Set up a logger for tracking issues in production
logger = logging.getLogger(__name__)


# ==============================================================================
# --- 1. CORE PAGES (Browsing & Viewing) ---
# ==============================================================================

def home(request):
    """
    Handles the main landing page (/). 
    Redirects logged-in users directly to their dashboard.
    """
    if request.user.is_authenticated:
        return redirect('gigs:dashboard')
        
    context = {'welcome_message': 'Welcome to Find My Gig!'}
    return render(request, 'gigs/home.html', context)


def gig_listings(request):
    """
    Handles the main Gig list page with dropdown filtering and sorting.
    Gigs whose deadline has passed are hidden unless ?show_past=1 is given.
    """
    gigs_queryset = Listing.objects.all()

    show_past = request.GET.get('show_past') == '1'
    if not show_past:
        gigs_queryset = gigs_queryset.filter(deadline__gte=timezone.localdate())

    # Extract filter and sort parameters from URL
    instrument_filter = request.GET.get('instrument', '')
    date_query = request.GET.get('date', '')
    sort_by = request.GET.get('sort', '')

    # Apply filters
    if instrument_filter:
        gigs_queryset = gigs_queryset.filter(req_instruments__icontains=instrument_filter)
    if date_query:
        try:
            deadline_filter = datetime.date.fromisoformat(date_query)
        except ValueError:
            # Malformed date: ignore the filter and leave the form field empty.
            date_query = ''
        else:
            gigs_queryset = gigs_queryset.filter(deadline=deadline_filter)

    # Apply sorting
    if sort_by == 'name':
        gigs_queryset = gigs_queryset.order_by('title')
    else:
        gigs_queryset = gigs_queryset.order_by('deadline') 
    
    # Track user interactions if logged in
    applied_gig_ids = []
    accepted_gig_ids = []
    bookmarked_gig_ids = []
    if request.user.is_authenticated:
        applied_gig_ids = Application.objects.filter(applicant=request.user).values_list('listing_id', flat=True)
        accepted_gig_ids = Application.objects.filter(
            applicant=request.user, status=Application.ACCEPTED).values_list('listing_id', flat=True)
        bookmarked_gig_ids = request.user.saved_gigs.values_list('id', flat=True)

    context = {
        'gigs': gigs_queryset,
        'applied_gig_ids': applied_gig_ids,
        'accepted_gig_ids': accepted_gig_ids,
        'selected_instrument': instrument_filter,
        'selected_date': date_query,
        'current_sort': sort_by,
        'show_past': show_past,
        'bookmarked_gig_ids': bookmarked_gig_ids,
    }

    return render(request, 'gigs/gig_listings.html', context)

def gig_detail(request, gig_id):
    """Shows the full details of a single gig, including the Google Map."""
    listing = get_object_or_404(Listing, id=gig_id)
    has_applied = False
    is_bookmarked = False
    has_reviewed = False 
    can_review = False
    
    if request.user.is_authenticated:
        has_applied = listing.applications_received.filter(applicant=request.user).exists()
        is_bookmarked = listing.bookmarks.filter(id=request.user.id).exists()
        has_reviewed = Review.objects.filter(reviewer=request.user, listing=listing).exists()
        can_review = gig_review_problem(request.user, listing) is None

    context = {
        'listing': listing, 
        'has_applied': has_applied,
        'is_bookmarked': is_bookmarked,
        'has_reviewed': has_reviewed,
        'can_review': can_review,
        'google_maps_frontend_key': settings.GOOGLE_MAPS_FRONTEND_KEY, 
    }
    
    return render(request, 'gigs/gig_detail.html', context)

def musicians_list(request):
    """
    Shows the page for browsing all registered musicians with a dropdown filter.
    """
    musicians = Musician.objects.all()
    instrument_filter = request.GET.get('instrument', '')
    
    if instrument_filter:
        musicians = musicians.filter(instruments__icontains=instrument_filter)
        
    return render(request, 'gigs/musicians_list.html', {
        'musicians': musicians, 
        'selected_instrument': instrument_filter
    })


def musician_detail(request, id):
    """
    Shows a specific musician's public profile and reviews.
    """
    musician = get_object_or_404(Musician, id=id)
    reviews = Review.objects.filter(reviewee=musician.user).order_by('-id')
    can_review = (request.user.is_authenticated
                  and musician_review_problem(request.user, musician) is None)
    
    context = {
        'musician': musician,
        'reviews': reviews,
        'can_review': can_review,
        'google_maps_frontend_key': settings.GOOGLE_MAPS_FRONTEND_KEY,
    }
    return render(request, 'gigs/musician_detail.html', context)


def bands_list(request):
    """
    Shows the page for browsing all registered bands.
    """
    bands = Band.objects.all()
    return render(request, 'gigs/bands_list.html', {'bands': bands})


def band_detail(request, id):
    """
    Shows the public profile for a specific band.
    """
    band = get_object_or_404(Band, id=id)
    context = {
        'band': band, 
        'google_maps_frontend_key': settings.GOOGLE_MAPS_FRONTEND_KEY,
    }
    return render(request, 'gigs/band_detail.html', context)


# ==============================================================================
# --- 2. USER DASHBOARD & MANAGEMENT ---
# ==============================================================================

@login_required
def dashboard(request):
    """
    The main hub for a logged-in user. Routes to the appropriate 
    Musician or Band template based on their profile type.
    """
    if hasattr(request.user, 'musician'):
        return render(request, 'gigs/musician_dashboard.html', {
            'profile': request.user.musician,
            'profile_type': 'musician'
        })
    elif hasattr(request.user, 'band'):
        return render(request, 'gigs/band_dashboard.html', {
            'profile': request.user.band,
            'profile_type': 'band'
        })
        
    return redirect('gigs:home')

    
@login_required
def my_applications(request):
    """
    Shows a Musician all the gigs they have applied for.
    """
    if not hasattr(request.user, 'musician'):
        return redirect('gigs:dashboard')

    user_applications = Application.objects.filter(applicant=request.user)
    context = {
        'applications': user_applications,
        'google_maps_frontend_key': settings.GOOGLE_MAPS_FRONTEND_KEY,
    }
    return render(request, 'gigs/my_applications.html', context)


@login_required
def my_bookmarks(request):
    """
    Shows a Musician their saved gigs.
    """
    if not hasattr(request.user, 'musician'):
        return redirect('gigs:dashboard')
        
    context = {
        'profile_type': 'musician',
        'saved_gigs': request.user.saved_gigs.all()
    }
    return render(request, 'gigs/my_bookmarks.html', context)


@login_required
def my_reviews(request):
    """Shows a user both the reviews they have received and written."""
    
    received_reviews = Review.objects.filter(reviewee=request.user).order_by('-id')
    
    written_reviews = Review.objects.filter(reviewer=request.user).order_by('-id')
    
    profile_type = 'musician' if hasattr(request.user, 'musician') else 'band'
    
    context = {
        'received_reviews': received_reviews,
        'written_reviews': written_reviews,
        'profile_type': profile_type
    }
    return render(request, 'gigs/my_reviews.html', context)


@login_required
def my_listings(request):
    """
    Shows a Band all the gigs they have currently posted.
    """
    try:
        band = request.user.band
        listings = Listing.objects.filter(band=band).prefetch_related(
            Prefetch('applications_received',
                     queryset=Application.objects.select_related('applicant__musician').order_by('date_applied')))
    except Band.DoesNotExist:
        listings = []
        
    return render(request, 'gigs/my_listings.html', {'listings': listings})


@login_required
def my_profile(request):
    """
    Shows the user's editable profile settings.
    """
    if hasattr(request.user, 'musician'):
        context = {
            'profile': request.user.musician,
            'profile_type': 'musician',
            'media_links': request.user.musician.media_links.all()
        }
        return render(request, 'gigs/my_profile_musician.html', context)
        
    elif hasattr(request.user, 'band'):
        context = {
            'profile': request.user.band,
            'profile_type': 'band',
            'media_links': []
        }
        return render(request, 'gigs/my_profile_band.html', context)
        
    return redirect('gigs:home')

@login_required
def my_reach_outs(request):
    """View for a Band to see the musicians they have contacted."""
    
    # Security check: Ensure the user actually has a band profile
    if not hasattr(request.user, 'band'):
        return redirect('gigs:dashboard') 
        
    # Fetch all interests sent by this band, newest first
    reach_outs = BandInterest.objects.filter(band=request.user.band).order_by('-created_at')
    
    context = {
        'reach_outs': reach_outs
    }
    
    return render(request, 'gigs/my_reach_outs.html', context)


@login_required
def create_gig(request):
    """
    Renders the gig creation form for Bands.
    """
    if not hasattr(request.user, 'band'):
        return redirect('gigs:dashboard')

    return render(request, 'gigs/create_gig.html')


# ==============================================================================
# --- 3. AUTHENTICATION & SETTINGS ---
# ==============================================================================

@transaction.atomic
def signup_choice(request):
    """
    Handles the custom signup flow, separating users into Musicians 
    or Bands upon creation to enforce correct relational mapping.
    """
    if request.user.is_authenticated:
        return redirect('gigs:home')

    user_form = UserSignUpForm()

    if request.method == 'POST':
        user_type = request.POST.get('user_type')
        user_form = UserSignUpForm(request.POST)

        if user_type not in ('musician', 'band'):
            return render(request, 'gigs/signup.html', {
                'user_form': user_form,
                'error_message': 'Please select an account type.'
            })

        if user_form.is_valid():
            user = user_form.save()
            
            # Create the associated profile object immediately
            if user_type == 'musician':
                Musician.objects.create(user=user)
            elif user_type == 'band':
                band_name = request.POST.get('band_name', '').strip()
                Band.objects.create(user=user, name=band_name)

            login(request, user)
            return redirect('gigs:my_profile')

        return render(request, 'gigs/signup.html', {'user_form': user_form})

    return render(request, 'gigs/signup.html')


@login_required
def update_profile(request):
    """
    Handles saving profile edits (bio, picture, instruments, etc.) via AJAX.
    Supports both JSON payloads and Multipart form data (for image uploads).

    All input is validated before anything is written, and the account, profile
    and media link changes are saved in one transaction. On invalid input nothing
    is changed and the response carries per-field errors:
    {'success': False, 'error': 'invalid' | 'username_taken', 'errors': {field: [messages]}}
    On success the links created this request are returned, in submitted order, as
    {'success': True, 'media_links': [{'id': ..., 'url': ...}]}
    """
    if request.method != 'POST':
        return redirect('gigs:my_profile')

    user = request.user

    if request.content_type and 'multipart' in request.content_type:
        data = request.POST
        files = request.FILES
    else:
        data = parse_json_body(request)
        if data is None:
            return json_error('invalid_json', 400)
        files = None

    is_musician = hasattr(user, 'musician')
    is_band = hasattr(user, 'band')
    if not (is_musician or is_band):
        return json_error('no_profile', 403)

    account_form = AccountEditForm(data, user=user)
    profile_form_class = MusicianEditForm if is_musician else BandEditForm
    profile_form = profile_form_class(data, files)

    # Validate both so every field error is reported together.
    account_valid = account_form.is_valid()
    profile_valid = profile_form.is_valid()
    if not (account_valid and profile_valid):
        errors = {}
        for form in (account_form, profile_form):
            errors.update({field: [str(e) for e in errs] for field, errs in form.errors.items()})
        code = 'username_taken' if 'username' in account_form.errors and \
            account_form.errors.as_data()['username'][0].code == 'username_taken' else 'invalid'
        return JsonResponse({'success': False, 'error': code, 'errors': errors}, status=400)

    account = account_form.cleaned_data
    cleaned = profile_form.cleaned_data
    try:
        with transaction.atomic():
            user.username = account['username']
            user.first_name = account['firstname']
            user.last_name = account['surname']
            user.save()

            if is_musician:
                profile = user.musician
                profile.bio = cleaned['about']
                if cleaned['age'] is not None:
                    profile.age = cleaned['age']
                profile.instruments = cleaned['instruments']
                if cleaned['profile_picture']:
                    profile.profile_picture = cleaned['profile_picture']
                profile.save()

                # Only this musician's links can be removed; new links are added
                # alongside the existing ones.
                if cleaned['delete_media']:
                    MediaLink.objects.filter(musician=profile, id__in=cleaned['delete_media']).delete()
                # Created one by one so each new link's id can be returned to the page.
                saved_links = [MediaLink.objects.create(musician=profile, url=url)
                               for url in cleaned['media_links']]
            else:
                profile = user.band
                profile.bio = cleaned['about']
                if cleaned['band_name']:
                    profile.name = cleaned['band_name']
                if cleaned['profile_picture']:
                    profile.profile_picture = cleaned['profile_picture']
                profile.save()
                saved_links = []
    except IntegrityError:
        # Lost a race for the username between validation and saving.
        return JsonResponse({'success': False, 'error': 'username_taken',
                             'errors': {'username': ['That username is already taken.']}},
                            status=400)

    return json_success(media_links=[{'id': link.id, 'url': link.url} for link in saved_links])


@login_required
def delete_account(request):
    """Permanently deletes the logged-in user and their cascaded profile."""
    if request.method == 'POST':
        user = request.user
        logout(request)
        user.delete()
        return json_success()
    return json_error('Invalid request method', 405)


# ==============================================================================
# --- 4. AJAX ACTIONS (Gigs, Apps, Bookmarks) ---
# ==============================================================================

@login_required
def create_gig_listing(request):
    """
    Allows a Band to post a new Gig via an AJAX payload.
    """
    if request.method == 'POST':
        if not hasattr(request.user, 'band'):
            return json_error('not_a_band', 403)

        data = parse_json_body(request)
        if data is None:
            return json_error('invalid_json', 400)
        title = str(data.get('title', '')).strip()
        req_instruments = str(data.get('req_instruments', '')).strip()
        deadline = data.get('date', '')
        description = str(data.get('description', '')).strip()
        location = str(data.get('location', '')).strip()

        if not all([title, req_instruments, deadline, description, location]):
            return json_error('missing_fields', 400)

        try:
            if datetime.date.fromisoformat(str(deadline)) < timezone.localdate():
                return json_error('invalid_data')
            listing = Listing.objects.create(
                band=request.user.band,
                title=title,
                req_instruments=req_instruments,
                deadline=deadline,
                description=description,
                location=location,
                is_urgent=False
            )
        except (ValidationError, ValueError):
            return json_error('invalid_data', 400)

        return JsonResponse({
            'success': True,
            'listing': {
                'id': listing.id,
                'title': listing.title,
                'req_instruments': listing.req_instruments,
                'deadline': str(listing.deadline),
                'location': listing.location,
                'description': listing.description,
            }
        })
        
    return json_error('Invalid request method', 405)

    
@login_required
def delete_listing(request, listing_id):
    """Allows a Band to delete their own listing."""
    if request.method == 'POST':
        if not hasattr(request.user, 'band'):
            return json_error('not_a_band', 403)
        try:
            listing = Listing.objects.get(id=listing_id, band=request.user.band)
            listing.delete()
            return json_success()
        except Listing.DoesNotExist:
            return json_error('not_found', 404)
    return json_error('invalid_request', 405)


def json_error(error, status=400):
    """
    Standard failure payload for the AJAX endpoints. The HTTP status says what
    kind of failure it was: 400 bad input, 403 not allowed (wrong role or not
    logged in), 404 not found, 405 wrong method.
    """
    return JsonResponse({'success': False, 'error': error}, status=status)


def json_success(**extra):
    """Standard success payload for the AJAX endpoints."""
    return JsonResponse({'success': True, **extra})


def parse_json_body(request):
    """Return the decoded JSON object in the request body, or None if it is malformed."""
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def listing_action(view_func):
    """
    Shared boilerplate for the AJAX endpoints that act on one Listing.
    Requires POST and a logged-in user (answering with JSON errors rather
    than redirects), then calls view_func(request, listing).
    """
    @functools.wraps(view_func)
    def wrapper(request, gig_id):
        if request.method != 'POST':
            return json_error('Invalid request', 405)
        if not request.user.is_authenticated:
            return json_error('not_logged_in', 403)
        try:
            listing = Listing.objects.get(id=gig_id)
        except Listing.DoesNotExist:
            return json_error('not_found', 404)
        return view_func(request, listing)
    return wrapper


@listing_action
def apply_gig(request, listing):
    """Creates an Application linking a Musician to a Gig. Bands cannot apply."""
    if not hasattr(request.user, 'musician'):
        return json_error('not_a_musician', 403)
    if listing.band.user == request.user:
        return json_error('own_gig', 403)
    if Application.objects.filter(applicant=request.user, listing=listing).exists():
        return json_error('already_applied', 400)
    if listing.deadline < timezone.localdate():
        return json_error('deadline_passed', 400)

    try:
        with transaction.atomic():
            Application.objects.create(applicant=request.user, listing=listing)
    except IntegrityError:
        # Lost a race with a concurrent identical request.
        return json_error('already_applied', 400)
    return json_success()


def _set_application_status(request, application_id, status):
    """
    Shared body of the accept/decline endpoints. Only the band that owns the
    application's listing may change it; anyone else gets the same 'not_found'
    as for a missing application, and nothing is changed.
    """
    if request.method != 'POST':
        return json_error('invalid_request', 405)
    if not request.user.is_authenticated:
        return json_error('not_logged_in', 403)
    if not hasattr(request.user, 'band'):
        return json_error('not_a_band', 403)
    try:
        application = Application.objects.get(id=application_id, listing__band=request.user.band)
    except Application.DoesNotExist:
        return json_error('not_found', 404)
    application.status = status
    application.save(update_fields=['status'])
    return json_success(status=application.status)


def accept_application(request, application_id):
    """Allows a Band to accept an application to one of its listings."""
    return _set_application_status(request, application_id, Application.ACCEPTED)


def decline_application(request, application_id):
    """Allows a Band to decline an application to one of its listings."""
    return _set_application_status(request, application_id, Application.DECLINED)


@listing_action
def withdraw_gig(request, listing):
    """Deletes an Application linking a Musician to a Gig."""
    Application.objects.filter(applicant=request.user, listing=listing).delete()
    return json_success()


@listing_action
def save_gig(request, listing):
    """Adds the Gig to the user's Bookmarked Gigs list."""
    listing.bookmarks.add(request.user)
    return json_success()


@listing_action
def unsave_gig(request, listing):
    """Removes the Gig from the user's Bookmarked Gigs list."""
    listing.bookmarks.remove(request.user)
    return json_success()


# ==============================================================================
# --- 5. REVIEWS & FEEDBACK ---
# ==============================================================================
@login_required
def submit_review(request, gig_id):
    """A musician accepted for a gig reviews the band behind it (see gigs/reviews.py)."""
    listing = get_object_or_404(Listing, id=gig_id)
    target_user = listing.band.user

    problem = gig_review_problem(request.user, listing)
    if problem:
        messages.error(request, problem)
        return redirect('gigs:gig_detail', gig_id=listing.id)

    form = ReviewForm(request.POST or None)
    status = 200
    if request.method == 'POST':
        if form.is_valid():
            try:
                with transaction.atomic():
                    Review.objects.create(
                        reviewer=request.user,
                        reviewee=target_user,
                        listing=listing,
                        rating=form.cleaned_data['rating'],
                        comment=form.cleaned_data['comment'],
                    )
            except IntegrityError:
                # A concurrent submission got there first.
                messages.error(request, "You have already left a review for this gig!")
                return redirect('gigs:gig_detail', gig_id=listing.id)
            messages.success(request, "Your review has been successfully published!")
            return redirect('gigs:gig_detail', gig_id=listing.id)
        status = 400

    context = {
        'listing': listing,
        'target_user': target_user,
        'form': form,
    }
    return render(request, 'gigs/gig_review.html', context, status=status)

@login_required
def submit_musician_review(request, musician_id):
    """A band reviews a musician it accepted for one of its gigs (see gigs/reviews.py)."""
    musician = get_object_or_404(Musician, id=musician_id)

    problem = musician_review_problem(request.user, musician)
    if problem:
        messages.error(request, problem)
        return redirect('gigs:musician_detail', id=musician_id)

    form = None
    status = 200
    if request.method == 'POST':
        form = ReviewForm({'rating': request.POST.get('rating'), 'comment': request.POST.get('feedback')})
        if form.is_valid():
            try:
                with transaction.atomic():
                    Review.objects.create(
                        reviewer=request.user,
                        reviewee=musician.user,
                        rating=form.cleaned_data['rating'],
                        comment=form.cleaned_data['comment'],
                    )
            except IntegrityError:
                messages.error(request, "You have already reviewed this musician.")
                return redirect('gigs:musician_detail', id=musician_id)
            messages.success(request, "Your review has been published.")
            return redirect('gigs:musician_detail', id=musician_id)
        status = 400

    return render(request, 'gigs/musician_review.html', {'musician': musician, 'form': form}, status=status)


@login_required
def send_interest(request, musician_id):
    """Allows a Band to send a simple interest message to a Musician via AJAX."""
    if request.method == 'POST':
        if not hasattr(request.user, 'band'):
            return json_error('Only bands can send interest.', 403)

        band = request.user.band
        try:
            musician = Musician.objects.get(id=musician_id)
        except Musician.DoesNotExist:
            return json_error('not_found', 404)
        data = parse_json_body(request)
        if data is None:
            return json_error('invalid_json', 400)
        message = str(data.get('message', '')).strip()

        if not message:
            return json_error('Message cannot be empty.', 400)

        if BandInterest.objects.filter(band=band, musician=musician).exists():
            return json_error('You have already reached out to this musician.', 400)

        BandInterest.objects.create(band=band, musician=musician, message=message)
        return json_success()
        
    return json_error('Invalid request method', 405)
    

@login_required
def my_inbox(request):
    """Shows a Musician all the interest messages they have received."""
    if not hasattr(request.user, 'musician'):
        return redirect('gigs:dashboard')

    messages = request.user.musician.received_interests.all().order_by('-created_at')
    return render(request, 'gigs/my_inbox.html', {'messages': messages})


@login_required
def delete_interest(request, interest_id):
    """Allows a Musician to delete an interest message from their inbox via AJAX."""
    if request.method == 'POST':
        try:
            musician = request.user.musician
            interest = BandInterest.objects.get(id=interest_id, musician=musician)
            interest.delete()
            return json_success()
        except (Musician.DoesNotExist, BandInterest.DoesNotExist):
            return json_error('not_found', 404)
            
    return json_error('Invalid request method', 405)