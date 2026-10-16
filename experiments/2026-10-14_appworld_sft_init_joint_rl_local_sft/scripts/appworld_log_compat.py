"""Local AppWorld log serialization compatibility; never changes requests or actions."""
def install_request_log_compatibility():
    import appworld.requester as requester
    stats = {'ellipsis_log_encodings': 0}

    def encode_ellipsis(value):
        stats['ellipsis_log_encodings'] += 1
        return {'__python_type__': 'Ellipsis', 'repr': 'Ellipsis'}

    def save(self, file_path):
        # Same encoder and writer as AppWorld, with one explicit logging-only type.
        # self.requests and actual API argument objects remain untouched.
        serialized = [requester.cast_dict(requester.jsonable_encoder(
            request, custom_encoder={type(Ellipsis): encode_ellipsis}))
            for request in self.requests]
        requester.write_jsonl(serialized, file_path, silent=True)

    requester.RequestTracker.save = save
    return stats
