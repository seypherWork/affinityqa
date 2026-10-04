"""Explicit technical amendment: fixed 180s deadline and shared-prefix serialization."""
from .metadata_agent import MetadataMovieAgent


class MetadataRuntimeAgent(MetadataMovieAgent):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.timeout=180
        self.manifest.update(inference_timeout_seconds=180,serialization='task-catalog-schema-profile-context-v1')

    def decision_input(self,request,schema):
        data=super().decision_input(request,schema)
        return {k:data[k] for k in ('task','catalog','output_schema','profile','cultural_context')}
