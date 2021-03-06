# Copyright 2015 SUSE LLC, Robert Schweikert
#
# This file is part of ec2deprecateimg.
#
# ec2deprecateimg is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ec2deprecateimg is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ec2deprecateimg. If not, see <http://www.gnu.org/licenses/>.

import boto
import boto.ec2
import ConfigParser
import datetime
import dateutil.relativedelta
import re

from .ec2utils import EC2Utils
from .ec2UtilsExceptions import *


class EC2DeprecateImg(EC2Utils):
    """Deprecate EC2 image(s) by tagging the image with 3 tags, Deprecated on,
       Removal date, and Replacement image."""

    def __init__(
            self,
            access_key=None,
            deprecation_period=6,
            deprecation_image_id=None,
            deprecation_image_name=None,
            deprecation_image_name_fragment=None,
            deprecation_image_name_match=None,
            force=None,
            image_virt_type=None,
            public_only=None,
            replacement_image_id=None,
            replacement_image_name=None,
            replacement_image_name_fragment=None,
            replacement_image_name_match=None,
            secret_key=None,
            verbose=None):
        EC2Utils.__init__(self)

        self.access_key = access_key
        self.deprecation_period = deprecation_period
        self.deprecation_image_id = deprecation_image_id
        self.deprecation_image_name = deprecation_image_name
        self.deprecation_image_name_fragment = deprecation_image_name_fragment
        self.deprecation_image_name_match = deprecation_image_name_match
        self.force = force
        self.image_virt_type = image_virt_type
        self.public_only = public_only
        self.replacement_image_id = replacement_image_id
        self.replacement_image_name = replacement_image_name
        self.replacement_image_name_fragment = replacement_image_name_fragment
        self.replacement_image_name_match = replacement_image_name_match
        self.secret_key = secret_key
        self.verbose = verbose

        self._set_deprecation_date()
        self._set_deletion_date()

        self.replacement_image_tag = None

    # ---------------------------------------------------------------------
    def _find_images_by_id(self, image_id, filter_replacement_image=None):
        """Find images by ID match"""
        images = []
        my_images = self._get_all_type_match_images(filter_replacement_image)
        for image in my_images:
            if image_id == image.id:
                images.append(image)
                # The framework guarantees unique image IDs
                return images

    # ---------------------------------------------------------------------
    def _find_images_by_name(self, image_name, filter_replacement_image=None):
        """Find images by exact name match"""
        images = []
        my_images = self._get_all_type_match_images(filter_replacement_image)
        for image in my_images:
            if not image.name:
                if filter_replacement_image:
                    msg = 'WARNING: Found image with no name, ignoring for '
                    msg += 'deprecation search. Image ID: %s' % image.id
                    print msg
                continue
            if image_name == image.name:
                images.append(image)

        return images

    # ---------------------------------------------------------------------
    def _find_images_by_name_fragment(
            self,
            name_fragment,
            filter_replacement_image=None):
        """Find images by string matching of the fragment with the name"""
        images = []
        my_images = self._get_all_type_match_images(filter_replacement_image)
        for image in my_images:
            if not image.name:
                if filter_replacement_image:
                    msg = 'WARNING: Found image with no name, ignoring for '
                    msg += 'deprecation search. Image ID: %s' % image.id
                    print msg
                continue
            if image.name.find(name_fragment) != -1:
                images.append(image)

        return images

    # ---------------------------------------------------------------------
    def _find_images_by_name_regex_match(
            self,
            expression,
            filter_replacement_image=None):
        """Find images by match the name with the given regular expression"""
        images = []
        my_images = self._get_all_type_match_images(filter_replacement_image)
        try:
            match = re.compile(expression)
        except:
            msg = 'Unable to complie regular expression "%s"' % expression
            raise EC2DeprecateImgException(msg)
        for image in my_images:
            if not image.name:
                if filter_replacement_image:
                    msg = 'WARNING: Found image with no name, ignoring for '
                    msg += 'deprecation search. Image ID: %s' % image.id
                    print msg
                continue
            if match.match(image.name):
                images.append(image)

        return images

    # ---------------------------------------------------------------------
    def _format_date(self, date):
        """Format the date to YYYYMMDD"""
        year = date.year
        month = date.month
        day = date.day
        date = '%s' % year
        for item in [month, day]:
            if item > 9:
                date += '%s' % item
            else:
                date += '0%s' % item

        return date

    # ---------------------------------------------------------------------
    def _get_all_type_match_images(self, filter_replacement_image=None):
        """Get all images that match thespecified virtualization type.
           All images owned by the account if not type is specified."""
        images = []
        my_images = self.ec2.get_all_images(owners='self')
        for image in my_images:
            if filter_replacement_image:
                if image.id == self.replacement_image_id:
                    if self.verbose:
                        msg = 'Ignore replacement image as potential target '
                        msg += 'for deprecation.'
                        print msg
                    continue
            if self.image_virt_type:
                if self.image_virt_type == image.virtualization_type:
                    images.append(img)
                else:
                    continue
            if self.public_only:
                launchPerm = image.get_launch_permissions().get('groups', None)
                if launchPerm:
                    for item in launchPerm:
                        if item == 'all':
                            images.append(image)
                            break
                continue
            images.append(image)

        return images

    # ---------------------------------------------------------------------
    def _get_images_to_deprecate(self):
        """Find images to deprecate"""
        images = None
        condition = None
        if self.deprecation_image_id:
            images = self._find_images_by_id(self.deprecation_image_id, True)
        elif self.deprecation_image_name:
            images = self._find_images_by_name(
                self.deprecation_image_name, True)
        elif self.deprecation_image_name_fragment:
            images = self._find_images_by_name_fragment(
                self.deprecation_image_name_fragment, True)
        elif self.deprecation_image_name_match:
            images = self._find_images_by_name_regex_match(
                self.deprecation_image_name_match, True)
        else:
            msg = 'No deprecation image condition set. Should not reach '
            msg += 'this point.'
            raise EC2DeprecateImgException(msg)

        return images

    # ---------------------------------------------------------------------
    def _set_deletion_date(self):
        """Set the date when the deprecation perios expires"""
        now = datetime.datetime.now()
        expire = now + dateutil.relativedelta.relativedelta(
            months=+self.deprecation_period)
        self.deletion_date = self._format_date(expire)

    # ---------------------------------------------------------------------
    def _set_deprecation_date(self):
        """Set the deprecation day in the YYYYMMDD format"""
        now = datetime.datetime.now()
        self.deprecation_date = self._format_date(now)

    # ---------------------------------------------------------------------
    def _set_replacement_image_info(self):
        """Find the replacement image information and create an identifier"""
        images = None
        condition = None
        if self.replacement_image_id:
            condition = self.replacement_image_id
            images = self._find_images_by_id(condition)
        elif self.replacement_image_name:
            condition = self.replacement_image_name
            images = self._find_images_by_name(condition)
        elif self.replacement_image_name_fragment:
            condition = self.replacement_image_name_fragment
            images = self._find_images_by_name_fragment(condition)
        elif self.replacement_image_name_match:
            condition = self.replacement_image_name_match
            images = self._find_images_by_name_regex_match(condition)
        else:
            msg = 'No replacement image condition set. Should not reach '
            msg += 'this point.'
            raise EC2DeprecateImgException(msg)

        if not images:
            msg = 'Replacement image not found, "%s" ' % condition
            msg += 'did not match any image.'
            raise EC2DeprecateImgException(msg)

        if len(images) > 1:
            msg = 'Replacement image ambiguity, the specified condition '
            msg += '"%s" return multiple replacement image options' % condition
            raise EC2DeprecateImgException(msg)

        image = images[0]
        self.replacement_image_id = image.id
        self.replacement_image_tag = '%s -- %s' % (image.id, image.name)

    # ---------------------------------------------------------------------
    def deprecate_images(self):
        """Deprecate images in the connected region"""
        self._connect()
        self._set_replacement_image_info()
        images = self._get_images_to_deprecate()
        if not images:
            if self.verbose:
                print 'No images to deprecate found'
            return False
        if self.verbose:
            print 'Deprecating images in region: ', self.region
            print '\tDeprecated on', self.deprecation_date
            print 'Removal date', self.deletion_date
            print 'Replacement image', self.replacement_image_tag
        for image in images:
            if not self.force and image.tags.get('Deprecated on', None):
                if self.verbose:
                    print '\t\tImage %s already tagged, skipping' % image.id
                continue
            image.add_tag('Deprecated on', self.deprecation_date)
            image.add_tag('Removal date', self.deletion_date)
            image.add_tag('Replacement image', self.replacement_image_tag)
            if self.verbose:
                print '\t\ttagged:%s\t%s' % (image.id, image.name)

    # ---------------------------------------------------------------------
    def print_deprecation_info(self):
        """Print information about the images that would be deprecated."""
        self._connect()
        self._set_replacement_image_info()
        images = self._get_images_to_deprecate()
        if not images:
            print 'No images to deprecate found'
            return True

        print 'Would deprecate images in region: ', self.region
        print '\tDeprecated on', self.deprecation_date
        print '\tRemoval date', self.deletion_date
        print '\tReplacement image', self.replacement_image_tag
        print '\tImages to deprecate:\n\t\tID\t\t\t\tName'
        for image in images:
            print '\t\t%s\t%s' % (image.id, image.name)

        return True
