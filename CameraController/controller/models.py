from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

class CameraSettings(models.Model):
    """
    Persistable camera control settings, including automatic and manual exposure.
    """
    brightness     = models.IntegerField(default=128, help_text="0–255, mid-point brightness")
    contrast       = models.IntegerField(default=64,  help_text="0–255, moderate contrast")
    saturation     = models.IntegerField(default=64,  help_text="0–255, moderate saturation")
    hue            = models.IntegerField(default=0,   help_text="0–180, default hue")
    gain           = models.IntegerField(default=0,   help_text="0–255, default gain (off)")

    # Exposure control: auto vs manual
    auto_exposure   = models.BooleanField(
        default=True,
        help_text="Enable automatic exposure (V4L2)"
    )
    manual_exposure = models.IntegerField(
        default=-6,
        validators=[MinValueValidator(-13), MaxValueValidator(0)],
        help_text="Manual exposure value (V4L2): range -13 (slow) to 0 (fast)"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Camera Settings"
        verbose_name_plural = "Camera Settings"

    def __str__(self):
        mode = "Auto" if self.auto_exposure else f"Manual ({self.manual_exposure})"
        return (
            f"Brightness={self.brightness}, Contrast={self.contrast}, "
            f"Saturation={self.saturation}, Gain={self.gain}, Exposure={mode}"
        )
