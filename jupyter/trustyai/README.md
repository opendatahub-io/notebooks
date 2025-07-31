Supports the use of TrustyAI

Features:

* TMaRCo detoxification from the notebooks ([https://issues.redhat.com/browse/RHOAIENG-12554], [https://issues.redhat.com/browse/RHOAIENG-12195])
  * This uses an "expert"/"anti-expert" architecture, which requires running these models locally.
    This meant that these dependencies (Pytorch, transformers and datasets) had to be added to the dependencies.
  * The use-case benefits from GPU acceleration, so the CUDA-enabled version of Pytorch was chosen.
