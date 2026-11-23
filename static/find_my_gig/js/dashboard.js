document.addEventListener('DOMContentLoaded', function () {

    const mediaState = createMediaState();
    let profileSaveInFlight = false;

    // ==========================================================================
    // --- 1. PROFILE MANAGEMENT ---
    // ==========================================================================
    
    const updateProfileBtn = document.getElementById('update-profile-btn');

    if (updateProfileBtn){
        updateProfileBtn.addEventListener('click', function(){

            const username = document.getElementById('profile-username')?.value.trim();
            
            if (!username) {
                showStatusMessage('status-message', 'Username is required', 'error');
                return;
            }

            const firstname = document.getElementById('firstname')?.value.trim() || '';   
            const surname = document.getElementById('surname')?.value.trim() || ''; 
            const bandName = document.getElementById('band-name')?.value.trim() || '';
            const profileAbout = document.getElementById('profile-about')?.value.trim() || '';
            const profileAge = document.getElementById('profile-age')?.value || '';
            const profileInstruments = document.getElementById('profile-instruments')?.value || '';
            const profilePictureInput = document.getElementById('profile-picture-input');
            const hasPicture = profilePictureInput?.files[0];

            if (profileSaveInFlight) {
                return;
            }
            const edits = mediaState.snapshot();
            const pendingMediaLinks = edits.links.map(link => link.url);
            const linksToDelete = edits.deletes;

            let requestConfig = {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken')
                }
            };

            // Handle Multipart Form Data (if image exists) vs JSON
            if (hasPicture){
                const formData = new FormData();
                formData.append('username', username);
                formData.append('firstname', firstname);
                formData.append('surname', surname);
                formData.append('band_name', bandName);
                formData.append('about', profileAbout);
                formData.append('age', profileAge);
                formData.append('instruments', profileInstruments);
                formData.append('profile_picture', profilePictureInput.files[0]);
                formData.append('media_links', JSON.stringify(pendingMediaLinks));
                formData.append('delete_media', JSON.stringify(linksToDelete));
                requestConfig.body = formData;
            } else {
                requestConfig.headers['Content-Type'] = 'application/json';
                requestConfig.body = JSON.stringify({
                    username: username,
                    firstname: firstname,   
                    surname: surname, 
                    band_name: bandName,
                    about: profileAbout,
                    age: profileAge,
                    instruments: profileInstruments,
                    media_links: pendingMediaLinks,
                    delete_media: linksToDelete
                });
            }

            profileSaveInFlight = true;
            updateProfileBtn.disabled = true;

            fetch('/dashboard/my-profile/update/', requestConfig)
                .then(readJsonResponse)
                .then(data => handleProfileUpdateResponse(data, edits))
                .catch(() => {
                    // Offline, HTML error page or expired session: nothing was
                    // saved, so keep the pending edits for a retry.
                    showStatusMessage('status-message', 'Could not save your profile, your changes are kept - please try again', 'error');
                })
                .finally(() => {
                    profileSaveInFlight = false;
                    updateProfileBtn.disabled = false;
                });
        });
    }

    function handleProfileUpdateResponse(data, edits) {
        if (data.success) {
            showStatusMessage('status-message', 'Profile updated successfully', 'success');
            const results = mediaState.commit(edits, data.media_links);
            reconcileSavedMediaLinks(results);
        } else if (data.error === 'username_taken') {
            showStatusMessage('status-message', 'That username is already taken, please choose another', 'error');
        } else if (data.errors) {
            const details = Object.entries(data.errors)
                .map(([field, messages]) => `${field}: ${messages.join(' ')}`)
                .join('; ');
            showStatusMessage('status-message', `Please fix: ${details}`, 'error');
        } else {
            showStatusMessage('status-message', 'Something went wrong, try again', 'error');
        }
    }

    // Profile Picture Preview Loader
    const profilePictureInput = document.getElementById('profile-picture-input');
    const profilePicturePreview = document.getElementById('profile-picture-preview');

    if (profilePictureInput && profilePicturePreview) {
        profilePictureInput.addEventListener('change', function () {
            const file = this.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function (e) {
                    profilePicturePreview.src = e.target.result;
                };
                reader.readAsDataURL(file);
            }
        });
    }

    // ==========================================================================
    // --- 2. MEDIA LINKS MANAGEMENT ---
    // ==========================================================================

    const addMediaBtn = document.getElementById('add-media-btn');
    if (addMediaBtn){
        addMediaBtn.addEventListener('click', function (e) {
            e.preventDefault()
            e.stopPropagation()

            const mediaInput = document.getElementById('media-link-input');
            const mediaUrl = mediaInput?.value.trim();

            if (!mediaUrl) {
                showStatusMessage('status-message', 'Please enter a URL', 'error');
                return;
            }

            if (!isValidUrl(mediaUrl)) {
                showStatusMessage('status-message', 'Please enter a valid link e.g. https://youtube.com/...', 'error');
                return;
            }

            const pendingId = mediaState.addPending(mediaUrl);
            addMediaLinkToList(mediaUrl, pendingId);
            mediaInput.value = '';
            showStatusMessage('status-message', 'Link added - press Update to save', 'success');
        });
    }

    const mediaList = document.getElementById('media-links-list');
    if (mediaList) {
        mediaList.addEventListener('click', function (e) {
            if (e.target.classList.contains('delete-media-btn')) {
                const mediaId = e.target.dataset.mediaId;
                const mediaItem = e.target.parentElement;

                mediaState.remove(mediaId);
                mediaItem.remove();
                if (mediaState.isPending(mediaId)) {
                    showStatusMessage('status-message', 'Link removed', 'success');
                } else {
                    showStatusMessage('status-message', 'Link removed - press Update to save changes', 'success');
                }
            }
        });
    }

    // ==========================================================================
    // --- 3. ACCOUNT DELETION ---
    // ==========================================================================

    const deleteAccountBtn = document.getElementById('delete-account-btn');
    if (deleteAccountBtn) {
        deleteAccountBtn.addEventListener('click', function (e) {
            e.preventDefault();
            const confirmed = confirm('Are you sure you want to delete your account? This cannot be undone.');

            if (confirmed){
                fetch('/dashboard/my-profile/delete-account/', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken'),
                        'Content-Type': 'application/json'
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        window.location.href = '/';
                    }
                })
                .catch(() => window.location.href = '/');
            }
        });
    }

    // ==========================================================================
    // --- 4. GIG & APPLICATION MANAGEMENT ---
    // ==========================================================================

    // Withdraw Application
    document.querySelectorAll('.withdraw-application-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const gigId = this.dataset.gigId;
            const applicationCard = this.closest('.listing-card');
            const confirmed = confirm('Are you sure you want to withdraw this application?');

            if (confirmed) {
                fetch(`/gigs/${gigId}/withdraw/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken'),
                        'Content-Type': 'application/json'
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        applicationCard.remove();
                        showStatusMessage('status-message', 'Application withdrawn', 'success');
                    }
                })
                .catch(() => {
                    applicationCard.remove();
                    showStatusMessage('status-message', 'Application withdrawn', 'success');
                });
            }
        });
    });

    // Accept / Decline an application (band)
    const APPLICATION_STATUS_LABELS = { accept: 'Accepted', decline: 'Declined' };
    ['accept', 'decline'].forEach(function (action) {
        document.querySelectorAll(`.${action}-application-btn`).forEach(function (btn) {
            btn.addEventListener('click', function () {
                const row = this.closest('.applicant-row');
                fetch(`/dashboard/my-listings/applications/${this.dataset.applicationId}/${action}/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken'),
                        'Content-Type': 'application/json'
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const label = APPLICATION_STATUS_LABELS[action];
                        const badge = row.querySelector('.application-status');
                        badge.textContent = label;
                        badge.className = `badge application-status status-${label.toLowerCase()} rounded-pill ms-2`;
                        row.querySelector('.accept-application-btn').disabled = (action === 'accept');
                        row.querySelector('.decline-application-btn').disabled = (action === 'decline');
                        showStatusMessage('status-message', `Application ${label.toLowerCase()}`, 'success');
                    } else {
                        showStatusMessage('status-message', data.message || data.error || 'Something went wrong', 'error');
                    }
                })
                .catch(() => showStatusMessage('status-message', 'Network error.', 'error'));
            });
        });
    });

    // Create Gig Listing
    const createGigBtn = document.getElementById('create-gig-btn');
    if (createGigBtn) {
        createGigBtn.addEventListener('click', function () {
            const gigTitle = document.getElementById('listing-title')?.value?.trim();
            const gigPosition = document.getElementById('gig-position')?.value;
            const gigDate = document.getElementById('gig-date')?.value;
            const gigDescription = document.getElementById('gig-description')?.value?.trim();
            const gigLocation = document.getElementById('gig-location')?.value?.trim();

            if (!gigTitle || !gigPosition || !gigDate || !gigDescription || !gigLocation) {
                showStatusMessage('status-message', 'Please fill out all fields', 'error');
                return;
            }

            const gigData = {
                title: gigTitle,
                req_instruments: gigPosition,
                date: gigDate,
                description: gigDescription,
                location: gigLocation
            };

            fetch('/dashboard/my-listings/create/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(gigData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showStatusMessage('status-message', 'Gig listing created successfully', 'success');
                    window.location.href = '/dashboard/my-listings/';
                } else {
                    showStatusMessage('status-message', 'Something went wrong, try again', 'error');
                }
            })
            .catch(() => showStatusMessage('status-message', 'Network error', 'error'));
        });
    }

    // Delete Own Listing
    const myListingsList = document.getElementById('my-listings-list');
    if (myListingsList) {
        myListingsList.addEventListener('click', function (e) {
            if (e.target.classList.contains('delete-listing-btn')) {
                const listingId = e.target.dataset.listingId;
                const listingCard = e.target.closest('.listing-card');
                const confirmed = confirm('Are you sure you want to delete this listing?');

                if (confirmed) {
                    fetch(`/dashboard/my-listings/${listingId}/delete/`, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': getCookie('csrftoken'),
                            'Content-Type': 'application/json'
                        }
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            listingCard.remove();
                            showStatusMessage('status-message', 'Listing deleted', 'success');
                        }
                    })
                    .catch(() => {
                        listingCard.remove();
                        showStatusMessage('status-message', 'Listing deleted', 'success');
                    });
                }
            }
        });
    }

    // Remove Saved Gig
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('remove-saved-gig-btn')) {
            e.preventDefault();
            const btn = e.target;
            const gigId = btn.dataset.gigId;
            const savedGigCard = btn.closest('.col-md-6');

            fetch(`/gigs/${gigId}/unsave/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    savedGigCard?.remove();
                    showStatusMessage('status-message', 'Gig removed from saved', 'success');
                } else {
                    showStatusMessage('status-message', 'Failed to remove bookmark', 'error');
                }
            })
            .catch(() => showStatusMessage('status-message', 'Failed to remove bookmark', 'error'));
        }
    });

    // ==========================================================================
    // --- 5. INBOX MANAGEMENT ---
    // ==========================================================================

    // Dismiss Inbox Message
    const inboxList = document.getElementById('inbox-list');
    if (inboxList) {
        inboxList.addEventListener('click', function(e) {
            if (e.target.classList.contains('delete-msg-btn')) {
                const msgId = e.target.dataset.msgId;
                const msgCard = document.getElementById(`msg-${msgId}`);

                fetch(`/dashboard/inbox/${msgId}/delete/`, {
                    method: 'POST',
                    headers: { 
                        'X-CSRFToken': getCookie('csrftoken'), 
                        'Content-Type': 'application/json' 
                    }
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        msgCard.remove();
                        showStatusMessage('status-message', 'Message dismissed.', 'success');
                    }
                })
                .catch(() => showStatusMessage('status-message', 'Failed to dismiss', 'error'));
            }
        });
    }
});

// ==========================================================================
// --- 6. HELPER FUNCTIONS ---
// ==========================================================================

/**
 * Parses a fetch response as JSON. Rejects when the body is not JSON (HTML error
 * page, login redirect) so callers treat it as a failure. A JSON body is passed
 * through even on a non-2xx status, so structured API errors can be shown.
 */
function readJsonResponse(response) {
    const contentType = response.headers && response.headers.get ? (response.headers.get('content-type') || '') : 'application/json';
    if (response.redirected || !contentType.includes('json')) {
        return Promise.reject(new Error('Unexpected non-JSON response'));
    }
    return response.json().then(function (data) {
        if (!data || typeof data !== 'object') {
            throw new Error('Unexpected response body');
        }
        if (!response.ok && data.success !== false) {
            data = Object.assign({}, data, { success: false });
        }
        return data;
    });
}

/**
 * After a confirmed save, marks each saved link as persisted: swaps its
 * pending id for the server id and removes the "not saved yet" label.
 */
function reconcileSavedMediaLinks(results) {
    results.forEach(function (result) {
        const btn = document.querySelector(`.delete-media-btn[data-media-id="${result.pendingId}"]`);
        if (!btn || !result.saved) {
            return;
        }
        btn.dataset.mediaId = String(result.saved.id);
        const label = btn.parentElement.querySelector('.pending-label');
        if (label) {
            label.remove();
        }
    });
}

function isValidUrl(url){
    try{
        new URL(url);
        return true;
    } catch{
        return false;
    }
}

function addMediaLinkToList(url, mediaId){
    const mediaList = document.getElementById('media-links-list');
    if (mediaList) {
        const listItem = document.createElement('li');
        
        const link = document.createElement('a');
        link.href = url;
        link.textContent = url;
        link.target = '_blank';

        const deleteBtn = document.createElement('button');
        deleteBtn.textContent = 'Delete File';
        deleteBtn.classList.add('delete-media-btn');
        deleteBtn.dataset.mediaId = mediaId;

        if (String(mediaId).startsWith('pending-')) {
            const pendingLabel = document.createElement('span');
            pendingLabel.textContent = ' (not saved yet)';
            pendingLabel.classList.add('pending-label');
            listItem.appendChild(link);
            listItem.appendChild(pendingLabel);
            listItem.appendChild(deleteBtn);
        } else {
            listItem.appendChild(link);
            listItem.appendChild(deleteBtn);
        }
        
        mediaList.appendChild(listItem);
    }
}