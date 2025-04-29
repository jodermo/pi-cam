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



class AppConfigSettings(models.Model):
    """Globale App-Konfiguration, inkl. Timelapse-Einstellungen."""

    enable_timelapse = models.BooleanField(default=True)
    timelapse_interval_minutes = models.PositiveIntegerField(default=1)

    timelapse_folder = models.CharField(
        max_length=255,
        default='timelapse',
        help_text="Unterordner von MEDIA_ROOT, in dem Timelapse-Bilder gespeichert werden."
    )

    capture_resolution_width = models.PositiveIntegerField(default=1280)
    capture_resolution_height = models.PositiveIntegerField(default=720)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AppConfig (Timelapse {'ON' if self.enable_timelapse else 'OFF'})"

    class Meta:
        verbose_name = "App Configuration"
        verbose_name_plural = "App Configurations"