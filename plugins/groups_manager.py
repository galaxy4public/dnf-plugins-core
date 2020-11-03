# groups_manager.py
# DNF plugin for managing comps groups metadata files
#
# Copyright (C) 2020 Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#

from __future__ import absolute_import
from __future__ import unicode_literals

import argparse
import libcomps
import re

from dnfpluginscore import _, logger
import dnf
import dnf.cli


RE_GROUP_ID_VALID = "-a-z0-9_.:"
RE_GROUP_ID = re.compile(r"^[{}]+$".format(RE_GROUP_ID_VALID))
RE_LANG = re.compile(r"^[-a-zA-Z0-9_.@]+$")
COMPS_XML_OPTIONS = {
    'default_explicit': True,
    'uservisible_explicit': True,
    'empty_groups': True}


def group_id_type(value):
    '''group id validator'''
    if not RE_GROUP_ID.match(value):
        raise argparse.ArgumentTypeError(_('Invalid group id'))
    return value


def translation_type(value):
    '''translated texts validator'''
    data = value.split(':', 2)
    if len(data) != 2:
        raise argparse.ArgumentTypeError(
            _("Invalid translated data, should be in form 'lang:text'"))
    lang, text = data
    if not RE_LANG.match(lang):
        raise argparse.ArgumentTypeError(_("Invalid/empty language for translated data"))
    return lang, text


def text_to_id(text):
    '''generate group id based on its name'''
    group_id = text.lower()
    group_id = re.sub('[^{}]'.format(RE_GROUP_ID_VALID), '', group_id)
    if not group_id:
        raise dnf.cli.CliError(
            _("Can't generate group id from '{}'. Please specify group id using --id.").format(
                text))
    return group_id


@dnf.plugin.register_command
class GroupsManagerCommand(dnf.cli.Command):
    aliases = ('groups-manager',)
    summary = _('create and edit groups metadata file')

    def __init__(self, cli):
        super(GroupsManagerCommand, self).__init__(cli)
        self.comps = libcomps.Comps()

    @staticmethod
    def set_argparser(parser):
        # input / output options
        parser.add_argument('--load', action='append', default=[],
                            metavar="<COMPS.XML>",
                            help=_('load groups metadata from file'))
        parser.add_argument('--save', action='append', default=[],
                            metavar="<COMPS.XML>",
                            help=_('save groups metadata to file'))
        parser.add_argument('--merge', metavar="<COMPS.XML>",
                            help=_('load and save groups metadata to file'))
        parser.add_argument('--print', action="store_true", default=False,
                            help=_('print the result metadata to stdout'))
        # group options
        parser.add_argument('--id', type=group_id_type,
                            help=_('group id'))
        parser.add_argument('-n', '--name', help=_('group name'))
        parser.add_argument('--description',
                            help=_('group description'))
        parser.add_argument('--display-order', type=int,
                            help=_('sort order override'))
        parser.add_argument('--translated-name', action='append', default=[],
                            metavar="LANG:TEXT", type=translation_type,
                            help=_('translated name for the group'))
        parser.add_argument('--translated-description', action='append', default=[],
                            metavar="LANG:TEXT", type=translation_type,
                            help=_('translated description for the group'))
        visible = parser.add_mutually_exclusive_group()
        visible.add_argument('--user-visible', dest="user_visible", action="store_true",
                             help="make the group user visible (default)")
        visible.add_argument('--not-user-visible', dest="user_visible", action="store_false",
                             help="make the group user invisible")

        # package list options
        # mandatory
        # optional
        # dependencies
        parser.add_argument('--remove', action="store_true", default=False,
                            help=_('remove packages from group instead of adding them'))

    def configure(self):
        # XXX require repos only when package list is present
        demands = self.cli.demands
        demands.sack_activation = True
        demands.available_repos = True

        # handle --merge option (shortcut to --load and --save the same file)
        if self.opts.merge:
            self.opts.load.insert(0, self.opts.merge)
            self.opts.save.append(self.opts.merge)

        # check that group is specified when editing is attempted
        if (self.opts.description
                or self.opts.display_order
                or self.opts.translated_name
                or self.opts.translated_description
                or self.opts.user_visible is not None):
            if not self.opts.id and not self.opts.name:
                raise dnf.cli.CliError(
                    _("Can't edit group without specifying it (use --id or --name)"))

    def load_input_files(self):
        """
        Loads all input xml files.
        Returns True if at least one file was successfuly loaded
        """
        file_loaded = False
        for file_name in self.opts.load:
            file_comps = libcomps.Comps()
            try:
                file_comps.fromxml_f(file_name)
            except (IOError, libcomps.ParserError) as err:
                logger.warning(_("Can't load file \"{}\": {}").format(file_name, err))
                # get_last_errors() output often contains duplicit lines, remove them
                seen = set()
                for error in file_comps.get_last_errors():
                    if error in seen:
                        continue
                    logger.warning(error.strip())
                    seen.add(error)
            else:
                self.comps += file_comps
                file_loaded = True
        return file_loaded

    def save_output_files(self):
        for file_name in self.opts.save:
            try:
                # xml_f returns a list of errors / log entries
                errors = self.comps.xml_f(file_name, xml_options=COMPS_XML_OPTIONS)
            except libcomps.XMLGenError as err:
                errors = [err]
            if errors:
                logger.error(''.join(errors).strip())

    def find_group(self, group_id, name):
        '''
        Try to find group according to command line parameters - first by id
        then by name.
        '''
        group = None
        if group_id:
            for grp in self.comps.groups:
                if grp.id == group_id:
                    group = grp
                    break
        if group is None and name:
            for grp in self.comps.groups:
                if grp.name == name:
                    group = grp
                    break
        return group

    def edit_group(self, group):
        '''
        Set attributes and package lists for selected group
        '''
        def langlist_to_strdict(lst):
            str_dict = libcomps.StrDict()
            for lang, text in lst:
                str_dict[lang] = text
            return str_dict

        # set group attributes
        if self.opts.name:
            group.name = self.opts.name
        if self.opts.description:
            group.desc = self.opts.description
        if self.opts.display_order:
            group.display_order = self.opts.display_order
        if self.opts.user_visible is not None:
            group.uservisible = self.opts.user_visible
        if self.opts.translated_name:
            group.name_by_lang = langlist_to_strdict(self.opts.translated_name)
        if self.opts.translated_description:
            group.desc_by_lang = langlist_to_strdict(self.opts.translated_description)

        # XXX edit packages lists

    def run(self):
        self.load_input_files()

        if self.opts.id or self.opts.name:
            # we are adding / editing a group
            group = self.find_group(group_id=self.opts.id, name=self.opts.name)
            if group is None:
                # create a new group
                if self.opts.remove:
                    raise dnf.exceptions.Error(_("Can't remove packages from non-existent group"))
                group = libcomps.Group()
                if self.opts.id:
                    group.id = self.opts.id
                    group.name = self.opts.id
                elif self.opts.name:
                    group_id = text_to_id(self.opts.name)
                    if self.find_group(group_id=group_id, name=None):
                        raise dnf.cli.CliError(
                            _("Group id '{}' generated from '{}' is duplicit. "
                              "Please specify group id using --id.").format(
                                  group_id, self.opts.name))
                    group.id = group_id
                self.comps.groups.append(group)
            self.edit_group(group)

        self.save_output_files()
        if self.opts.print or (not self.opts.save):
            print(self.comps.xml_str(xml_options=COMPS_XML_OPTIONS))
