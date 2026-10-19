"""vLLM 0.10.2 NVML ordinal lookup compatibility; CUDA visibility stays bound to GPU0 UUID."""
import os
if os.environ.get('JOINT_VLLM_GPU0_COMPAT')=='1':
    from vllm.platforms.interface import Platform
    from vllm.third_party import pynvml
    def uuid_physical_id(cls,device_id):
        expected='GPU-2044de33-9504-3cdf-451a-e9196cbdb21a'
        if os.environ.get('CUDA_VISIBLE_DEVICES')!=expected or device_id!=0:
            raise RuntimeError('UUID compatibility supports only the verified single physical GPU0')
        pynvml.nvmlInit()
        try:
            handle=pynvml.nvmlDeviceGetHandleByUUID(expected)
            index=pynvml.nvmlDeviceGetIndex(handle)
            if index!=0:raise RuntimeError('GPU UUID is no longer physical GPU0')
            return index
        finally:pynvml.nvmlShutdown()
    Platform.device_id_to_physical_device_id=classmethod(uuid_physical_id)
