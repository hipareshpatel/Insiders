"""The object calls the backup before a write uses (backup.py), for the hand-made sinks of the job tests."""


class BackupObjects:
    @property
    def objects(self) -> dict:
        return self.__dict__.setdefault("_objects", {})

    def put_object(self, key, body, content_type="application/json"):
        self.objects[key] = body

    def get_object(self, key):
        return self.objects.get(key)

    def list_objects(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))
