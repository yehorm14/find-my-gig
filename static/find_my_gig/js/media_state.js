/**
 * Pending media-link edit state for the profile page.
 *
 * Holds one coherent queue of unsaved edits: links added but not yet saved
 * (each with a stable, never-reused id) and persisted link ids waiting to be
 * deleted. Kept free of DOM access so it can be unit tested under Node.
 */
(function (root) {
    function createMediaState() {
        let counter = 0;
        let pending = [];      // [{ id: 'pending-N', url }]
        let toDelete = [];     // persisted link ids (strings)

        return {
            addPending(url) {
                counter += 1;
                const id = 'pending-' + counter;
                pending.push({ id: id, url: url });
                return id;
            },

            isPending(id) {
                return String(id).startsWith('pending-');
            },

            // Removes a queued add or schedules a persisted link for deletion.
            remove(id) {
                id = String(id);
                if (this.isPending(id)) {
                    pending = pending.filter(function (item) { return item.id !== id; });
                } else if (!toDelete.includes(id)) {
                    toDelete.push(id);
                }
            },

            // Copy of the edits to send; later edits do not alter it.
            snapshot() {
                return {
                    links: pending.map(function (item) { return { id: item.id, url: item.url }; }),
                    deletes: toDelete.slice()
                };
            },

            hasChanges() {
                return pending.length > 0 || toDelete.length > 0;
            },

            // Drops exactly the edits in `snapshot` after a confirmed save, keeping
            // anything queued while the request was in flight. Returns the pairing
            // of each pending id with the persisted link the server created.
            commit(snapshot, savedLinks) {
                toDelete = toDelete.filter(function (id) { return !snapshot.deletes.includes(id); });

                const sentIds = snapshot.links.map(function (item) { return item.id; });
                const pendingIds = new Set(pending.map(function (item) { return item.id; }));
                pending = pending.filter(function (item) { return !sentIds.includes(item.id); });

                const saved = Array.isArray(savedLinks) ? savedLinks : [];
                return snapshot.links.map((item, index) => {
                    const persistedLink = saved[index] || null;
                    if (persistedLink && !pendingIds.has(item.id)) {
                        // The link was deleted locally after it was submitted.
                        this.remove(persistedLink.id);
                    }
                    return { pendingId: item.id, saved: persistedLink };
                });
            }
        };
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { createMediaState: createMediaState };
    } else {
        root.createMediaState = createMediaState;
    }
})(typeof window !== 'undefined' ? window : this);
