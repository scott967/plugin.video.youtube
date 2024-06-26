# -*- coding: utf-8 -*-
"""

    Copyright (C) 2014-2016 bromix (plugin.video.youtube)
    Copyright (C) 2016-2018 plugin.video.youtube

    SPDX-License-Identifier: GPL-2.0-only
    See LICENSES/GPL-2.0-only for more information.
"""

from __future__ import absolute_import, division, unicode_literals

from traceback import format_stack

from ..abstract_plugin import AbstractPlugin
from ...compatibility import xbmcplugin
from ...constants import (
    BUSY_FLAG,
    CHECK_SETTINGS,
    PLAYLIST_PATH,
    PLAYLIST_POSITION,
    REROUTE,
    SLEEPING,
    VIDEO_ID,
)
from ...exceptions import KodionException
from ...items import (
    audio_listitem,
    directory_listitem,
    image_listitem,
    uri_listitem,
    video_listitem,
    video_playback_item,
)
from ...player import XbmcPlaylist


class XbmcPlugin(AbstractPlugin):
    _LIST_ITEM_MAP = {
        'AudioItem': audio_listitem,
        'DirectoryItem': directory_listitem,
        'ImageItem': image_listitem,
        'SearchItem': directory_listitem,
        'SearchHistoryItem': directory_listitem,
        'NewSearchItem': directory_listitem,
        'NextPageItem': directory_listitem,
        'VideoItem': video_listitem,
        'WatchLaterItem': directory_listitem,
    }

    _PLAY_ITEM_MAP = {
        'AudioItem': audio_listitem,
        'UriItem': uri_listitem,
        'VideoItem': video_playback_item,
    }

    def __init__(self):
        super(XbmcPlugin, self).__init__()
        self.handle = None

    def run(self, provider, context, refresh=False):
        self.handle = context.get_handle()
        ui = context.get_ui()

        if ui.get_property(BUSY_FLAG).lower() == 'true':
            if ui.busy_dialog_active():
                xbmcplugin.endOfDirectory(
                    self.handle,
                    succeeded=False,
                    updateListing=True,
                )

                playlist = XbmcPlaylist('auto', context, retry=3)
                position, remaining = playlist.get_position()
                items = playlist.get_items()
                playlist.clear()

                context.log_warning('Multiple busy dialogs active - '
                                    'playlist cleared to avoid Kodi crash')

                if position and items:
                    path = items[position - 1]['file']
                    old_path = ui.get_property(PLAYLIST_PATH)
                    old_position = ui.get_property(PLAYLIST_POSITION)
                    if (old_position and position == int(old_position)
                            and old_path and path == old_path):
                        if remaining:
                            position += 1
                        else:
                            items = None

                if items:
                    max_wait_time = 30
                    while ui.busy_dialog_active():
                        max_wait_time -= 1
                        if max_wait_time < 0:
                            context.log_error('Multiple busy dialogs active - '
                                              'extended busy period')
                            break
                        context.sleep(1)

                    context.log_warning('Multiple busy dialogs active - '
                                        'reloading playlist')

                    num_items = playlist.add_items(items)
                    if position:
                        max_wait_time = min(position, num_items)
                    else:
                        position = 1
                        max_wait_time = num_items
                    while ui.busy_dialog_active() or playlist.size() < position:
                        max_wait_time -= 1
                        if max_wait_time < 0:
                            context.log_error('Multiple busy dialogs active - '
                                              'unable to restart playback')
                            break
                        context.sleep(1)
                    else:
                        playlist.play_playlist_item(position)

                ui.clear_property(BUSY_FLAG)
                ui.clear_property(PLAYLIST_PATH)
                ui.clear_property(PLAYLIST_POSITION)
                return False

            ui.clear_property(BUSY_FLAG)
            ui.clear_property(PLAYLIST_PATH)
            ui.clear_property(PLAYLIST_POSITION)

        if ui.get_property(SLEEPING):
            context.wakeup()
            ui.clear_property(SLEEPING)

        if ui.get_property(CHECK_SETTINGS):
            provider.reset_client()
            settings = context.get_settings(refresh=True)
            ui.clear_property(CHECK_SETTINGS)
        else:
            settings = context.get_settings()

        if settings.setup_wizard_enabled():
            provider.run_wizard(context)

        try:
            route = ui.get_property(REROUTE)
            if route:
                function_cache = context.get_function_cache()
                result, options = function_cache.run(
                    provider.navigate,
                    seconds=None,
                    _cacheparams=function_cache.PARAMS_NONE,
                    _oneshot=True,
                    context=context.clone(route),
                )
                ui.clear_property(REROUTE)
            else:
                result, options = provider.navigate(context)
        except KodionException as exc:
            result = options = None
            if provider.handle_exception(context, exc):
                context.log_error('XbmcRunner.run - {exc}:\n{details}'.format(
                    exc=exc, details=''.join(format_stack())
                ))
                ui.on_ok('Error in ContentProvider', exc.__str__())

        focused = ui.get_property(VIDEO_ID) if refresh else None
        item_count = 0
        if isinstance(result, (list, tuple)):
            show_fanart = settings.fanart_selection()
            result = [
                self._LIST_ITEM_MAP[item.__class__.__name__](
                    context,
                    item,
                    show_fanart=show_fanart,
                    focused=focused,
                )
                for item in result
                if item.__class__.__name__ in self._LIST_ITEM_MAP
            ]
            item_count = len(result)
        elif result.__class__.__name__ in self._PLAY_ITEM_MAP:
            result = self._set_resolved_url(context, result)

        if item_count:
            succeeded = xbmcplugin.addDirectoryItems(
                self.handle, result, item_count
            )
            cache_to_disc = options.get(provider.RESULT_CACHE_TO_DISC, True)
            update_listing = options.get(provider.RESULT_UPDATE_LISTING, False)
        else:
            succeeded = bool(result)
            cache_to_disc = False
            update_listing = True

        xbmcplugin.endOfDirectory(
            self.handle,
            succeeded=succeeded,
            updateListing=update_listing,
            cacheToDisc=cache_to_disc,
        )
        return succeeded

    def _set_resolved_url(self, context, base_item):
        resolved = False
        uri = base_item.get_uri()

        if base_item.playable:
            ui = context.get_ui()
            if not context.is_plugin_path(uri) and ui.busy_dialog_active():
                ui.set_property(BUSY_FLAG)
                playlist = XbmcPlaylist('auto', context)
                position, _ = playlist.get_position()
                items = playlist.get_items()
                if position and items:
                    ui.set_property(PLAYLIST_PATH, items[position - 1]['file'])
                    ui.set_property(PLAYLIST_POSITION, str(position))

            item = self._PLAY_ITEM_MAP[base_item.__class__.__name__](
                context,
                base_item,
                show_fanart=context.get_settings().fanart_selection(),
                for_playback=True,
            )
            xbmcplugin.setResolvedUrl(self.handle,
                                      succeeded=True,
                                      listitem=item)
            resolved = True
        elif context.is_plugin_path(uri):
            context.log_debug('Redirecting to: |{0}|'.format(uri))
            context.execute('RunPlugin({0})'.format(uri))
        else:
            context.log_debug('Running script: |{0}|'.format(uri))
            context.execute('RunScript({0})'.format(uri))

        return resolved
