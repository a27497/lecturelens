"""Reuse the offline wire fixture through the E3 factory."""

import flash_fake
from lecturelens_real_eval.tutor.flash_e3_app import experiment_app


def create_app():
    flash_fake.experiment_app = experiment_app
    return flash_fake.create_app()
