"""
Review eligibility rules and input validation, shared by both review flows.

Policy (see also the Review model docstring):
  * Gig review: the reviewer must be a musician with an Accepted Application
    for the listing. The reviewee is the band that owns the listing.
  * Musician review: the reviewer must be a band, and the musician must have an
    Accepted Application for one of that band's listings.
  * There is no "completed gig" state in the data model, so an accepted
    application is what counts as the relationship; Pending and Declined do not.
"""
from django import forms

from gigs.models import Application, Review


class ReviewForm(forms.Form):
    rating = forms.IntegerField(
        min_value=1, max_value=5,
        error_messages={'required': 'Please select a rating from 1 to 5.',
                        'invalid': 'Please select a rating from 1 to 5.',
                        'min_value': 'Rating must be between 1 and 5.',
                        'max_value': 'Rating must be between 1 and 5.'})
    comment = forms.CharField(
        max_length=1000,
        error_messages={'required': 'Please write a comment.'})


def gig_review_problem(reviewer, listing):
    """Return a user-facing reason the reviewer cannot review this gig, or None."""
    if reviewer == listing.band.user:
        return "You cannot review your own gig."
    if not hasattr(reviewer, 'musician'):
        return "Only musicians can review a gig."
    if not Application.objects.filter(
            applicant=reviewer, listing=listing, status=Application.ACCEPTED).exists():
        return "You can only review gigs where your application was accepted."
    if Review.objects.filter(reviewer=reviewer, listing=listing).exists():
        return "You have already left a review for this gig!"
    return None


def musician_review_problem(reviewer, musician):
    """Return a user-facing reason the reviewer cannot review this musician, or None."""
    if reviewer == musician.user:
        return "You cannot review yourself."
    if not hasattr(reviewer, 'band'):
        return "Only bands can review musicians."
    if not Application.objects.filter(
            applicant=musician.user, listing__band=reviewer.band, status=Application.ACCEPTED).exists():
        return "You can only review musicians you have accepted for one of your gigs."
    if Review.objects.filter(reviewer=reviewer, reviewee=musician.user, listing__isnull=True).exists():
        return "You have already reviewed this musician."
    return None
