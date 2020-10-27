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

import libcomps

from dnfpluginscore import _, logger
from dnf.cli.option_parser import OptionParser
import dnf
import dnf.cli


@dnf.plugin.register_command
class GroupsManagerCommand(dnf.cli.Command):
    aliases = ('groups-manager',)
    summary = _('create and edit groups metadata file')

    def __init__(self, cli):
        super(GroupsManagerCommand, self).__init__(cli)
        self.comps = libcomps.Comps()

    @staticmethod
    def set_argparser(parser):
        parser.add_argument('--load', action='append', default=[],
                            metavar="<COMPS.XML>",
                            help=_('load groups metadata from file'))
        parser.add_argument('--merge', metavar="<COMPS.XML>",
                            help=_('load and save groups metadata to file'))
        parser.add_argument('--print', action="store_true", default=False,
                            help=_('print the result metadata to stdout'))
        parser.add_argument('--save', action='append', default=[],
                            metavar="<COMPS.XML>",
                            help=_('save groups metadata to file'))

    def configure(self):
        demands = self.cli.demands
        #demands.available_repos = True
        #demands.sack_activation = True

        # handle --merge option (shortcut to --load and --save the same file)
        if self.opts.merge:
            self.opts.load.insert(0, self.opts.merge)
            self.opts.save.append(self.opts.merge)

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
            else:
                self.comps += file_comps
                file_loaded = True
        return file_loaded

    def save_output(self):
        for file_name in self.opts.save: 
            try:
                # xml_f returns a list of errors / log entries
                errors = self.comps.xml_f(file_name)
            except libcomps.XMLGenError as err:
                errors = [err]
            if errors:
                logger.warning(''.join(errors).strip())

    def run(self):
        self.load_input_files()
        self.save_output()
        if self.opts.print or (not self.opts.save):
            print(self.comps.xml_str())
