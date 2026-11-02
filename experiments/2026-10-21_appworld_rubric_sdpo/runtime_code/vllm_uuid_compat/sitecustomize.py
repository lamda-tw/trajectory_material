"""vLLM 0.10.2 NVML ordinal lookup compatibility; CUDA visibility stays bound to GPU1 UUID."""
import os
if os.environ.get('JOINT_VLLM_GPU1_COMPAT')=='1':
    from vllm.platforms.interface import Platform
    from vllm.third_party import pynvml
    def uuid_physical_id(cls,device_id):
        expected='GPU-35170b76-56ce-240a-19c0-0c092a3e8501'
        if os.environ.get('CUDA_VISIBLE_DEVICES')!=expected or device_id!=0:
            raise RuntimeError('UUID compatibility supports only the verified single physical GPU1')
        pynvml.nvmlInit()
        try:
            handle=pynvml.nvmlDeviceGetHandleByUUID(expected)
            index=pynvml.nvmlDeviceGetIndex(handle)
            if index!=1:raise RuntimeError('GPU UUID is no longer physical GPU1')
            return index
        finally:pynvml.nvmlShutdown()
    Platform.device_id_to_physical_device_id=classmethod(uuid_physical_id)
