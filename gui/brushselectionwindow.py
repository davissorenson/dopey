# This file is part of MyPaint.
# Copyright (C) 2007 by Martin Renold <martinxyz@gmx.ch>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"select brush window"
import gtk, pango
gdk = gtk.gdk
from gettext import gettext as _

import windowing
import pixbuflist, dialogs, brushmanager
from brushlib import brushsettings

class Window(windowing.SubWindow):
    def __init__(self, app):
        windowing.SubWindow.__init__(self, app)
        self.last_selected_brush = None

        self.set_title(_('Brush selection'))
        self.set_role('Brush selector')
        self.connect('delete-event', self.app.hide_window_cb)

        self.groupselector = GroupSelector(self.app)
        self.brushgroups = BrushGroupsList(self.app)

        #main container
        vbox = gtk.VBox()
        self.add(vbox)

        self.scroll = scroll = gtk.ScrolledWindow()
        scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroll.add_with_viewport(self.brushgroups)

        expander = self.expander = gtk.Expander(label='')
        expander.set_expanded(False)
        expander.add(get_common_settings_widget(app))

        al = gtk.Alignment(0.0, 0.0, 1.0, 1.0)
        al.add(self.groupselector)
        al.set_padding(2,2,4,4)
        vbox.pack_start(al, expand=False)
        vbox.pack_start(gtk.HSeparator(), expand=False)
        vbox.pack_start(scroll, expand=True)
        vbox.pack_start(gtk.HSeparator(), expand=False)
        vbox.pack_start(expander, expand=False, fill=False)

def get_common_settings_widget(app):
    """Return a widget with controls for manipulating common settings"""

    cmn = ['radius_logarithmic', 'opaque', 'hardness']
    common_settings = [s for s in brushsettings.settings_visible if s.cname in cmn]
    settings_box = gtk.VBox()

    def value_changed_cb(adj, index, app):
        app.brush.settings[index].set_base_value(adj.get_value())

    def get_setting_widget(setting):
        """Return a widget to control a single setting"""

        adj = app.brush_adjustment[s.cname]
        adj.connect('value-changed', value_changed_cb, s.index, app)

        l = gtk.Label(s.name)
        l.set_alignment(0, 0.5)

        h = gtk.HScale(adj)
        h.set_digits(2)
        h.set_draw_value(True)
        h.set_value_pos(gtk.POS_LEFT)

        box = gtk.HBox()
        box.pack_start(l)
        box.pack_start(h)
        return box

    for s in common_settings:
        settings_box.pack_start(get_setting_widget(s))

    return settings_box

class BrushList(pixbuflist.PixbufList):
    def __init__(self, app, group):
        self.app = app
        self.bm = app.brushmanager
        self.brushes = self.bm.groups[group]
        pixbuflist.PixbufList.__init__(self, self.brushes, 48, 48,
                                       namefunc = lambda x: x.name,
                                       pixbuffunc = lambda x: x.preview)
        self.set_selected(self.bm.selected_brush)
        self.bm.brushes_observers.append(self.brushes_modified_cb)
        self.bm.selected_brush_observers.append(self.brush_selected_cb)

    def brushes_modified_cb(self, brushes):
        if brushes is self.brushes:
            self.update()

    def brush_selected_cb(self, brush):
        self.set_selected(brush)

    def remove_brush(self, brush):
        self.brushes.remove(brush)
        for f in self.bm.brushes_observers: f(self.brushes)

    def insert_brush(self, idx, brush):
        self.brushes.insert(idx, brush)
        for f in self.bm.brushes_observers: f(self.brushes)

    def drag_begin_cb(self, widget, context):
        preview = self.bm.selected_brush.preview
        preview = preview.scale_simple(preview.get_width()//2, preview.get_height()//2, gtk.gdk.INTERP_BILINEAR)
        self.drag_source_set_icon_pixbuf(preview)
        pixbuflist.PixbufList.drag_begin_cb(self, widget, context)

    #def drag_end_cb(self, widget, context):
    #    pixbuflist.PixbufList.drag_end_cb(self, widget, context)

    def on_drag_data(self, copy, source_widget, brush_name, target_idx):
        assert source_widget, 'cannot handle drag data from another app'
        b, = [b for b in source_widget.brushes if b.name == brush_name]
        if source_widget is self:
            copy = False
        else:
            if b in self.brushes:
                source_widget.remove_brush(b)
                self.remove_brush(b)
                self.insert_brush(target_idx, b)
                return True
        if not copy:
            source_widget.remove_brush(b)
        self.insert_brush(target_idx, b)
        return True

    def on_select(self, brush):
        # keep the color setting
        color = self.app.brush.get_color_hsv()

        # brush changed on harddisk?
        if brush.reload_if_changed():
            for brushes in self.bm.groups.itervalues():
                for f in self.bm.brushes_observers: f(brushes)

        self.bm.select_brush(brush)
        self.app.brush.set_color_hsv(color)

class BrushGroupsList(gtk.VBox):
    def __init__(self, app):
        gtk.VBox.__init__(self)
        self.app = app
        self.bm = app.brushmanager
        self.group_widgets = {}
        self.update()
        self.bm.groups_observers.append(self.groups_modified_cb)

    def groups_modified_cb(self):
        self.update()

    def update(self):
        for group in self.group_widgets.keys():
            if group not in self.bm.groups:
                # this leaks around 2MB of memory, not sure why
                # (no real problem, this is only when deleting/renaming groups)
                del self.group_widgets[group]

        self.foreach(self.remove)

        for group in self.bm.active_groups:
            if group in self.group_widgets:
                w = self.group_widgets[group]
            else:
                w = BrushList(self.app, group)
            self.group_widgets[group] = w
            self.pack_start(w, expand=False, fill=False, padding=3)

        self.show_all()

class GroupSelector(gtk.DrawingArea):
    def __init__(self, app):
        gtk.DrawingArea.__init__(self)

        self.app = app
        self.bm = app.brushmanager
        self.bm.groups_observers.append(self.active_groups_changed_cb)

        self.drag_dest_set(gtk.DEST_DEFAULT_MOTION | gtk.DEST_DEFAULT_DROP,
                [('LIST_ITEM', gtk.TARGET_SAME_APP, pixbuflist.DRAG_ITEM_NAME)],
                gdk.ACTION_COPY)
        self.connect('drag-motion', self.drag_motion_cb)
        self.connect('drag-data-received', self.drag_data_received_cb)

        self.connect("expose-event", self.expose_cb)
        self.connect("button-press-event", self.button_press_cb)
        self.connect("motion-notify-event", self.motion_notify_cb)
        self.connect("leave-notify-event", self.leave_notify_cb)
        self.set_events(gdk.EXPOSURE_MASK |
                        gdk.BUTTON_PRESS_MASK |
                        gdk.BUTTON_RELEASE_MASK |
                        gdk.POINTER_MOTION_MASK
                        )
        self.idx2group = {}
        self.layout = None
        self.gtkstate_prelight_group = None
        self.gtkstate_active_group = None
        self.set_tooltip_text(_('try right click, middle click or Ctrl click'))

    def active_groups_changed_cb(self):
        self.queue_draw()

    def expose_cb(self, widget, event):
        cr = self.window.cairo_create()
        width, height = self.window.get_size()

        style = self.get_style()

        c = style.bg[gtk.STATE_NORMAL]
        cr.set_source_rgb(c.red_float, c.green_float, c.blue_float)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        c = style.text[gtk.STATE_NORMAL]
        cr.set_source_rgb(c.red_float, c.green_float, c.blue_float)
        layout = cr.create_layout()
        layout.set_width(width*pango.SCALE)
        layout.set_font_description(style.font_desc)

        all_groups = list(sorted(self.bm.groups.keys()))

        idx = 0
        text = ''
        attr = pango.AttrList()
        self.idx2group = {}
        pad_s = u"\u202f"  # NARROW NO-BREAK SPACE
        sp_s = pad_s + u"\u200b"  # ZERO WIDTH SPACE

        import platform
        if platform.system() == 'Windows':
            # workaround for https://gna.org/bugs/?15192
            pad_s = ''
            sp_s = ' '

        for group in all_groups:
            group_label = brushmanager.translate_group_name(group)
            u = pad_s + group_label + pad_s
            s = u.encode('utf8')
            idx_start = idx
            for c in s:
                self.idx2group[idx] = group
                idx += 1
            
            # Note the difference in terminology here
            bg_state = fg_state = gtk.STATE_NORMAL
            if group == self.gtkstate_active_group: # activated the menu
                bg_state = fg_state = gtk.STATE_ACTIVE
            elif group in self.bm.active_groups: # those groups visible
                bg_state = fg_state = gtk.STATE_SELECTED
            elif group == self.gtkstate_prelight_group:
                bg_state = fg_state = gtk.STATE_PRELIGHT

            # always use the STATE_SELECTED fg if the group is visible
            if group in self.bm.active_groups:
                fg_state = gtk.STATE_SELECTED 

            c = style.bg[bg_state]
            attr.insert(pango.AttrBackground(c.red, c.green, c.blue, idx_start, idx))
            c = style.fg[fg_state]
            attr.insert(pango.AttrForeground(c.red, c.green, c.blue, idx_start, idx))

            text += u + sp_s
            idx += len(sp_s.encode("utf8"))

        layout.set_text(text)
        layout.set_attributes(attr)
        
        leading = style.font_desc.get_size() / 6
        vmargin = leading // pango.SCALE
        layout.set_spacing(leading)
        
        w, h = layout.get_pixel_size()
        h += 2*vmargin
        cr.move_to(0, vmargin)
        cr.show_layout(layout)

        self.set_size_request(-1, h)

        self.layout = layout

    def group_at(self, x, y):
        x, y = int(x), int(y) # avoid warning
        i, d = self.layout.xy_to_index(x*pango.SCALE, y*pango.SCALE)
        return self.idx2group.get(i)

    def button_press_cb(self, widget, event):
        if event.type != gdk.BUTTON_PRESS:
            return # double or tripple click
        group = self.group_at(event.x, event.y)

        if event.button in [1, 2]:
            if not group:
                return

            active_groups = self.bm.active_groups[:]

            if event.state & gdk.CONTROL_MASK or event.state & gdk.SHIFT_MASK or event.button == 2:
                # toggle group visibility
                if group in active_groups:
                    active_groups.remove(group)
                else:
                    active_groups += [group]
            else:
                # group solo
                active_groups = [group]

            self.bm.set_active_groups(active_groups)

        elif event.button == 3:
            # context menu
            self.gtkstate_active_group = group
            self.queue_draw()
            menu = self.context_menu(group)
            menu.popup(None,None,None, event.button, event.time, group)

    def motion_notify_cb(self, widget, event):
        old_prelight_group = self.gtkstate_prelight_group
        self.gtkstate_prelight_group = self.group_at(event.x, event.y)
        if self.gtkstate_prelight_group != old_prelight_group:
            self.queue_draw()

    def leave_notify_cb(self, widget, event):
        old_prelight_group = self.gtkstate_prelight_group
        self.gtkstate_prelight_group = None
        if self.gtkstate_prelight_group != old_prelight_group:
            self.gtkstate_prelight_group = None
            self.queue_draw()

    def context_menu(self, group):
        m = gtk.Menu()
        menu = []
        menu += [ (_("New group..."), self.create_group_cb) ]
        if group:
            menu += [ (_("Rename group..."), self.rename_group_cb),
                      (_("Export group..."), self.export_group_cb),
                      (_("Delete group..."), self.delete_group_cb)]
        for label, callback in menu:
            mi = gtk.MenuItem(label)
            mi.connect('activate', callback, group)
            m.append(mi)
        m.connect('selection-done', self.menu_finished_cb)
        m.show_all()
        return m

    def menu_finished_cb(self, menushell):
        self.gtkstate_active_group = None
        self.queue_draw()

    def create_group_cb(self, w, group):
        new_group = dialogs.ask_for_name(self, _('Create group'), '')
        if new_group:
            self.bm.create_group(new_group)

    def rename_group_cb(self, w, old_group):
        new_group = dialogs.ask_for_name(self, _('Rename group'), old_group)
        if not new_group:
            return
        if new_group not in self.bm.groups:
            self.bm.rename_group(old_group, new_group)
        else:
            dialogs.error(self, _('A group with this name already exists!'))

    def export_group_cb(self, w, group):
        format_id, filename = dialogs.save_dialog(_("Export brush pack..."), None,
                                 [(_("MyPaint brush package (*.zip)"), "*.zip")],
                                 default_format = (0, ".zip"))
        if filename is not None:
            self.bm.export_group(group, filename)

    def delete_group_cb(self, w, group):
        if dialogs.confirm(self, _('Really delete group %s?') % brushmanager.translate_group_name(group)):
            self.bm.delete_group(group)
            if group in self.bm.groups:
                dialogs.error(self, _('This group can not be deleted (try to make it empty first).'))

    def drag_data_received_cb(self, widget, context, x, y, selection, targetType, time):
        group = self.group_at(x,y)
        source = context.get_source_widget()
        # ensure, that drop comes from BrushList and targets some group
        if not group or not isinstance(source, BrushList):
            context.finish(False, False, time)
            return
        target = self.bm.groups[group]
        brush = self.bm.get_brush_by_name(selection.data)
        if brush in target:
            source.brushes.remove(brush)
            changed = source.brushes
        else:
            target.append(brush)
            changed = target
        for f in self.bm.brushes_observers: f(changed)
        context.finish(True, False, time)

    def drag_motion_cb(self, widget, context, x, y, time):
        context.drag_status(gdk.ACTION_COPY, time)
        old_prelight_group = self.gtkstate_prelight_group
        self.gtkstate_prelight_group = self.group_at(x,y)
        if self.gtkstate_prelight_group != old_prelight_group:
            self.queue_draw()
