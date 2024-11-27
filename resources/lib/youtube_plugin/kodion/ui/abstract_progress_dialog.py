# -*- coding: utf-8 -*-
"""

    Copyright (C) 2014-2016 bromix (plugin.video.youtube)
    Copyright (C) 2016-2018 plugin.video.youtube

    SPDX-License-Identifier: GPL-2.0-only
    See LICENSES/GPL-2.0-only for more information.
"""

from __future__ import absolute_import, division, unicode_literals

from ..compatibility import string_type


class AbstractProgressDialog(object):
    def __init__(self,
                 dialog,
                 heading,
                 message='',
                 total=None,
                 message_template=None,
                 template_params=None):
        self._dialog = dialog()
        self._dialog.create(heading, message)

        self._position = None
        self._total = int(total) if total else 100

        self._message = message
        self._message_template = message_template
        self._template_params = template_params or {}

        # simple reset because KODI won't do it :(
        self.update(position=0)

    def __enter__(self):
        return self

    def __exit__(self, exc_type=None, exc_val=None, exc_tb=None):
        self.close()

    def get_total(self):
        return self._total

    def get_position(self):
        return self._position

    def close(self):
        if self._dialog:
            self._dialog.close()
            self._dialog = None

    def is_aborted(self):
        return getattr(self._dialog, 'iscanceled', bool)()

    def set_total(self, total):
        self._total = int(total)

    def reset_total(self, new_total, **kwargs):
        self._total = int(new_total)
        self.update(position=0, **kwargs)

    def update_total(self, new_total, **kwargs):
        self._total = int(new_total)
        self.update(steps=0, **kwargs)

    def grow_total(self, new_total=None, delta=None):
        if delta:
            delta = int(delta)
            self._total += delta
        elif new_total:
            total = int(new_total)
            if total > self._total:
                self._total = total
        return self._total

    def update(self, steps=1, position=None, message=None, **template_params):
        if not self._dialog:
            return

        if position is None:
            self._position += steps
        else:
            self._position = position

        if not self._total:
            percent = 0
        elif self._position >= self._total:
            percent = 100
            self._total = self._position
        else:
            percent = int(100 * self._position / self._total)

        if isinstance(message, string_type):
            self._message = message
        elif self._message_template:
            if template_params:
                self._template_params.update(template_params)
            else:
                self._template_params['current'] = self._position
                self._template_params['total'] = self._total
            message = self._message_template.format(**self._template_params)
            self._message = message

        self._dialog.update(
            percent=percent,
            message=self._message,
        )
