# -*- coding: utf-8 -*-
"""

    Copyright (C) 2014-2016 bromix (plugin.video.youtube)
    Copyright (C) 2016-2018 plugin.video.youtube

    SPDX-License-Identifier: GPL-2.0-only
    See LICENSES/GPL-2.0-only for more information.
"""

from __future__ import absolute_import, division, unicode_literals

import copy
import time

from ..youtube_exceptions import LoginException


def process(mode, provider, context, sign_out_refresh=True):
    addon_id = context.get_param('addon_id', None)
    access_manager = context.get_access_manager()
    localize = context.localize
    ui = context.get_ui()

    def _do_logout():
        if addon_id:
            refresh_tokens = access_manager.get_dev_refresh_token(addon_id)
            client = provider.get_client(context)
            if refresh_tokens:
                for _refresh_token in set(refresh_tokens):
                    try:
                        client.revoke(_refresh_token)
                    except LoginException:
                        pass
            access_manager.update_dev_access_token(
                addon_id, access_token='', refresh_token=''
            )
        else:
            refresh_tokens = access_manager.get_refresh_token()
            client = provider.get_client(context)
            if refresh_tokens:
                for _refresh_token in set(refresh_tokens):
                    try:
                        client.revoke(_refresh_token)
                    except LoginException:
                        pass
            access_manager.update_access_token(
                access_token='', refresh_token=''
            )
        provider.reset_client()

    def _do_login(_for_tv=False):
        _client = provider.get_client(context)

        try:
            if _for_tv:
                json_data = _client.request_device_and_user_code_tv()
            else:
                json_data = _client.request_device_and_user_code()
        except LoginException:
            _do_logout()
            raise

        interval = int(json_data.get('interval', 5))
        if interval > 60:
            interval = 5
        device_code = json_data['device_code']
        user_code = json_data['user_code']
        verification_url = json_data.get('verification_url')
        if verification_url:
            verification_url = verification_url.lstrip('https://www.')
        else:
            verification_url = 'youtube.com/activate'

        text = [localize('sign.go_to') % ui.bold(verification_url),
                '[CR]%s %s' % (localize('sign.enter_code'),
                               ui.bold(user_code))]
        text = ''.join(text)

        with ui.create_progress_dialog(
                heading=localize('sign.in'), text=text, background=False
        ) as dialog:
            steps = ((10 * 60) // interval)  # 10 Minutes
            dialog.set_total(steps)
            for _ in range(steps):
                dialog.update()
                try:
                    if _for_tv:
                        json_data = _client.request_access_token_tv(device_code)
                    else:
                        json_data = _client.request_access_token(device_code)
                except LoginException:
                    _do_logout()
                    raise

                log_data = copy.deepcopy(json_data)
                if 'access_token' in log_data:
                    log_data['access_token'] = '<redacted>'
                if 'refresh_token' in log_data:
                    log_data['refresh_token'] = '<redacted>'
                context.log_debug('Requesting access token: |{data}|'.format(
                    data=log_data
                ))

                if 'error' not in json_data:
                    _access_token = json_data.get('access_token', '')
                    _refresh_token = json_data.get('refresh_token', '')
                    if not _access_token and not _refresh_token:
                        _expires_in = 0
                    else:
                        _expires_in = (int(json_data.get('expires_in', 3600))
                                       + time.time())
                    return _access_token, _expires_in, _refresh_token

                if json_data['error'] != 'authorization_pending':
                    message = json_data['error']
                    title = '%s: %s' % (context.get_name(), message)
                    ui.show_notification(message, title)
                    context.log_error('Error requesting access token: |error|'
                                      .format(error=message))

                if dialog.is_aborted():
                    break

                context.sleep(interval)
        return '', 0, ''

    if mode == 'out':
        _do_logout()
        if sign_out_refresh:
            ui.refresh_container()

    elif mode == 'in':
        ui.on_ok(localize('sign.twice.title'), localize('sign.twice.text'))

        tv_token = _do_login(_for_tv=True)
        access_token, expires_in, refresh_token = tv_token
        # abort tv login
        context.log_debug('YouTube-TV Login:'
                          ' Access Token |{0}|,'
                          ' Refresh Token |{1}|,'
                          ' Expires |{2}|'
                          .format(access_token != '',
                                  refresh_token != '',
                                  expires_in))
        if not access_token and not refresh_token:
            provider.reset_client()
            if addon_id:
                access_manager.update_dev_access_token(addon_id)
            else:
                access_manager.update_access_token('')
            ui.refresh_container()
            return

        kodi_token = _do_login(_for_tv=False)
        access_token, expires_in, refresh_token = kodi_token
        # abort kodi login
        context.log_debug('YouTube-Kodi Login:'
                          ' Access Token |{0}|,'
                          ' Refresh Token |{1}|,'
                          ' Expires |{2}|'
                          .format(access_token != '',
                                  refresh_token != '',
                                  expires_in))
        if not access_token and not refresh_token:
            provider.reset_client()
            if addon_id:
                access_manager.update_dev_access_token(addon_id)
            else:
                access_manager.update_access_token('')
            ui.refresh_container()
            return

        provider.reset_client()

        if addon_id:
            access_manager.update_dev_access_token(
                addon_id, *list(zip(tv_token, kodi_token))
            )
        else:
            access_manager.update_access_token(
                *list(zip(tv_token, kodi_token))
            )

        ui.refresh_container()
