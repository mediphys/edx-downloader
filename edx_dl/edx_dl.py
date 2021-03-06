#!/usr/bin/env python
# -*- coding: utf-8 -*-

# python 2/3 compatibility imports
from __future__ import print_function
from __future__ import unicode_literals

try:
    import builtins
except ImportError:
    import __builtin__ as builtins

try:
    from http.cookiejar import CookieJar
except ImportError:
    from cookielib import CookieJar

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

try:
    from urllib.request import urlopen
    from urllib.request import build_opener
    from urllib.request import install_opener
    from urllib.request import HTTPCookieProcessor
    from urllib.request import Request
    from urllib.request import URLError
except ImportError:
    from urllib2 import urlopen
    from urllib2 import build_opener
    from urllib2 import install_opener
    from urllib2 import HTTPCookieProcessor
    from urllib2 import Request
    from urllib2 import URLError

# we alias the raw_input function for python 3 compatibility
try:
    input = raw_input
except NameError:
    pass

import argparse
import getpass
import json
import os
import os.path
import re
import sys


from collections import namedtuple
from datetime import timedelta, datetime
from functools import partial
from multiprocessing.dummy import Pool as ThreadPool
from subprocess import Popen, PIPE

from bs4 import BeautifulSoup

OPENEDX_SITES = {
    'edx': {
        'url': 'https://courses.edx.org',
        'courseware-selector': ('nav', {'aria-label': 'Course Navigation'}),
    },
    'stanford': {
        'url': 'https://lagunita.stanford.edu',
        'courseware-selector': ('nav', {'aria-label': 'Course Navigation'}),
    },
    'usyd-sit': {
        'url': 'http://online.it.usyd.edu.au',
        'courseware-selector': ('nav', {'aria-label': 'Course Navigation'}),
    },
    'fun': {
        'url': 'https://www.france-universite-numerique-mooc.fr',
        'courseware-selector': ('section', {'aria-label': 'Menu du cours'}),
    },
    'gwu-seas': {
        'url': 'http://openedx.seas.gwu.edu',
        'courseware-selector': ('nav', {'aria-label': 'Course Navigation'}),
    },
    'gwu-open': {
        'url': 'http://mooc.online.gwu.edu',
        'courseware-selector': ('nav', {'aria-label': 'Course Navigation'}),
    },
}
BASE_URL = OPENEDX_SITES['edx']['url']
EDX_HOMEPAGE = BASE_URL + '/login_ajax'
LOGIN_API = BASE_URL + '/login_ajax'
DASHBOARD = BASE_URL + '/dashboard'
COURSEWARE_SEL = OPENEDX_SITES['edx']['courseware-selector']

YOUTUBE_VIDEO_ID_LENGTH = 11

Course = namedtuple('Course', ['name', 'url', 'state'])
Section = namedtuple('Section', ['position', 'name', 'url'])
SubSection = namedtuple('SubSection', ['url', 'units'])
Unit = namedtuple('Unit', ['video_youtube_url', 'sub_url'])


# To replace the print function, the following function must be placed
# before any other call for print
def print(*objects, **kwargs):
    """
    Overload the print function to adapt for the encoding bug in Windows
    console.

    It will try to convert text to the console encoding before printing to
    prevent crashes.
    """
    try:
        stream = kwargs.get('file', None)
        if stream is None:
            stream = sys.stdout
        enc = stream.encoding
        if enc is None:
            enc = sys.getdefaultencoding()
    except AttributeError:
        return builtins.print(*objects, **kwargs)

    texts = []
    for object in objects:
        try:
            if type(object) is bytes:
                if sys.version_info < (3, 0):
                    # in python 2 bytes must be converted to str before decode
                    object = str(object)
                original_text = object.decode(enc, errors='replace')
            else:
                if sys.version_info < (3, 0):
                    object = unicode(object)
                original_text = object.encode(enc, errors='replace').decode(enc, errors='replace')
        except UnicodeEncodeError:
            original_text = unicode(object).encode(enc, errors='replace').decode(enc, errors='replace')
        texts.append(original_text)
    return builtins.print(*texts, **kwargs)


def change_openedx_site(site_name):
    global BASE_URL
    global EDX_HOMEPAGE
    global LOGIN_API
    global DASHBOARD
    global COURSEWARE_SEL

    if site_name not in OPENEDX_SITES.keys():
        print("OpenEdX platform should be one of: %s" % ', '.join(OPENEDX_SITES.keys()))
        sys.exit(2)

    BASE_URL = OPENEDX_SITES[site_name]['url']
    EDX_HOMEPAGE = BASE_URL + '/login_ajax'
    LOGIN_API = BASE_URL + '/login_ajax'
    DASHBOARD = BASE_URL + '/dashboard'
    COURSEWARE_SEL = OPENEDX_SITES[site_name]['courseware-selector']


def display_courses(courses):
    """
    List the courses that the user has enrolled.
    """

    print('You can access %d courses' % len(courses))
    for i, (name, _, state) in enumerate(courses, 1):
        print('%d - [%s] - %s' % (i, state, name))


def get_courses_info(url, headers):
    """
    Extracts the courses information from the dashboard.
    """
    dash = get_page_contents(url, headers)
    soup = BeautifulSoup(dash)
    courses_soup = soup.find_all('article', 'course')
    courses = []
    for course_soup in courses_soup:
        course_name = course_soup.h3.text.strip()
        course_url = None
        course_state = 'Not yet'
        try:
            # started courses include the course link in the href attribute
            course_url = BASE_URL + course_soup.a['href']
            if course_url.endswith('info') or course_url.endswith('info/'):
                course_state = 'Started'
        except KeyError:
            pass

        courses.append(Course(name=course_name, url=course_url, state=course_state))
    return courses


def get_selected_course(courses):
    """
    Retrieve the course that the user selected.
    """
    num_of_courses = len(courses)

    c_number = None
    while True:
        c_number = int(input('Enter Course Number: '))

        if c_number not in range(1, num_of_courses+1):
            print('Enter a valid number between 1 and ', num_of_courses)
            continue
        elif courses[c_number - 1].state != 'Started':
            print('The course has not started!')
            continue
        else:
            break

    selected_course = courses[c_number - 1]
    return selected_course


def _get_initial_token(url):
    """
    Create initial connection to get authentication token for future
    requests.

    Returns a string to be used in subsequent connections with the
    X-CSRFToken header or the empty string if we didn't find any token in
    the cookies.
    """
    cj = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cj))
    install_opener(opener)
    opener.open(url)

    for cookie in cj:
        if cookie.name == 'csrftoken':
            return cookie.value

    return ''


def get_available_sections(url, headers):

    def _make_url(section_soup):  # FIXME: Extract from here and test
        return BASE_URL + section_soup.ul.find('a')['href']

    def _get_section_name(section_soup):  # FIXME: Extract from here and test
        return section_soup.h3.a.string.strip()

    courseware = get_page_contents(url, headers)
    soup = BeautifulSoup(courseware)
    sections_soup = soup.find_all('div', attrs={'class': 'chapter'})

    sections = [Section(position=idx,
                        name=_get_section_name(section_soup),
                        url=_make_url(section_soup))
                for idx, section_soup in enumerate(sections_soup, 1)]

    return sections


def get_page_contents(url, headers):
    """
    Get the contents of the page at the URL given by url. While making the
    request, we use the headers given in the dictionary in headers.
    """
    result = urlopen(Request(url, None, headers))
    try:
        charset = result.headers.get_content_charset(failobj="utf-8")  # for python3
    except:
        charset = result.info().getparam('charset') or 'utf-8'
    return result.read().decode(charset)


def directory_name(initial_name):
    import string
    allowed_chars = string.digits + string.ascii_letters + " _."
    result_name = ""
    for ch in initial_name:
        if allowed_chars.find(ch) != -1:
            result_name += ch
    return result_name if result_name != "" else "course_folder"


def edx_json2srt(o):
    output = ''
    for i, (s, e, t) in enumerate(zip(o['start'], o['end'], o['text'])):
        if t == "":
            continue
        output += str(i) + '\n'
        s = datetime(1, 1, 1) + timedelta(seconds=s/1000.)
        e = datetime(1, 1, 1) + timedelta(seconds=e/1000.)
        output += "%02d:%02d:%02d,%03d --> %02d:%02d:%02d,%03d" % \
            (s.hour, s.minute, s.second, s.microsecond/1000,
             e.hour, e.minute, e.second, e.microsecond/1000) + '\n'
        output += t + "\n\n"
    return output


def edx_get_subtitle(url, headers):
    """
    Return a string with the subtitles content from the url or None if no
    subtitles are available.
    """
    try:
        json_string = get_page_contents(url, headers)
        json_object = json.loads(json_string)
        return edx_json2srt(json_object)
    except URLError as e:
        print('[warning] edX subtitles (error:%s)' % e.reason)
        return None
    except ValueError as e:
        print('[warning] edX subtitles (error:%s)' % e.message)
        return None


def edx_login(url, headers, username, password):
    post_data = urlencode({'email': username,
                           'password': password,
                           'remember': False}).encode('utf-8')
    request = Request(url, post_data, headers)
    response = urlopen(request)
    resp = json.loads(response.read().decode('utf-8'))
    return resp


def parse_args():
    """
    Parse the arguments/options passed to the program on the command line.
    """
    parser = argparse.ArgumentParser(prog='edx-dl',
                                     description='Get videos from the OpenEdX platform',
                                     epilog='For further use information,'
                                     'see the file README.md',)
    # positional
    parser.add_argument('course_id',
                        nargs='*',
                        action='store',
                        default=None,
                        help='target course id '
                        '(e.g., https://courses.edx.org/courses/BerkeleyX/CS191x/2013_Spring/info/)'
                        )

    # optional
    parser.add_argument('-u',
                        '--username',
                        action='store',
                        help='your edX username (email)')
    parser.add_argument('-p',
                        '--password',
                        action='store',
                        help='your edX password')
    parser.add_argument('-f',
                        '--format',
                        dest='format',
                        action='store',
                        default=None,
                        help='format of videos to download')
    parser.add_argument('-s',
                        '--with-subtitles',
                        dest='subtitles',
                        action='store_true',
                        default=False,
                        help='download subtitles with the videos')
    parser.add_argument('-o',
                        '--output-dir',
                        action='store',
                        dest='output_dir',
                        help='store the files to the specified directory',
                        default='Downloaded')
    parser.add_argument('-x',
                        '--platform',
                        action='store',
                        dest='platform',
                        help='OpenEdX platform, currently either "edx", "stanford" or "usyd-sit"',
                        default='edx')
    parser.add_argument('-l',
                        '--list',
                        dest='list',
                        action='store_true',
                        default=False,
                        help='list available courses without downloading')

    args = parser.parse_args()
    return args


def edx_get_headers():
    headers = {
        'User-Agent': 'edX-downloader/0.01',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
        'Referer': EDX_HOMEPAGE,
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': _get_initial_token(EDX_HOMEPAGE),
    }
    return headers


def extract_subsection(url, headers):
    """
    Parses a webpag and extracts its resources e.g. video_url, sub_url, etc.
    """
    print("Processing '%s'..." % url)
    page = get_page_contents(url, headers)

    re_splitter = re.compile(r'data-streams=(?:&#34;|").*1.0[0]*:')
    re_subs = re.compile(r'data-transcript-translation-url=(?:&#34;|")([^"&]*)(?:&#34;|")')
    re_units = re_splitter.split(page)[1:]
    units = []
    for unit_html in re_units:
        video_id = unit_html[:YOUTUBE_VIDEO_ID_LENGTH]
        sub_url = None
        match_subs = re_subs.search(unit_html)
        if match_subs:
            sub_url = BASE_URL + match_subs.group(1) + "/en" + "?videoId=" + video_id
        units.append(Unit(video_youtube_url='http://youtube.com/watch?v=' + video_id,
                          sub_url=sub_url))

    # Try to download some extra videos which is referred by iframe
    re_extra_youtube = re.compile(r'//w{0,3}\.youtube.com/embed/([^ \?&]*)[\?& ]')
    extra_ids = re_extra_youtube.findall(page)
    for extra_id in extra_ids:
        units.append(Unit(video_youtube_url='http://youtube.com/watch?v=' + extra_id[:YOUTUBE_VIDEO_ID_LENGTH]))

    section_info = SubSection(url=url, units=units)
    return section_info


def _extract_urls_from_subsections(subsections):
    """
    This function is temporary, it exists only for compatible reasons, it
    extracts the list of video urls and subtitles from a list of
    page_resources.
    """
    video_urls = []
    sub_urls = []
    for subsection in subsections:
        for unit in subsection.units:
            video_urls.append(unit.video_youtube_url)
            sub_urls.append(unit.sub_url)
    return video_urls, sub_urls


def extract_all_subsections(urls, headers):
    # for development purposes you may want to uncomment this line
    # to test serial execution, and comment all the pool related ones
    # all_resources = [extract_subsection(url, headers) for url in urls]
    mapfunc = partial(extract_subsection, headers=headers)
    pool = ThreadPool(20)
    all_resources = pool.map(mapfunc, urls)
    pool.close()
    pool.join()
    video_urls, sub_urls = _extract_urls_from_subsections(all_resources)
    return video_urls, sub_urls


def display_sections(course_name, sections):
    """
    List the weeks for the given course.
    """
    num_sections = len(sections)
    print('%s has %d sections so far' % (course_name, num_sections))
    for i, section in enumerate(sections, 1):
        print('%d - Download %s videos' % (i, section.name))
    print('%d - Download them all' % (num_sections + 1))


def get_selected_sections(sections):
    """
    Retrieve the section(s) that the user selected.
    """
    num_sections = len(sections)
    number = int(input('Enter Your Choice: '))
    while number > num_sections + 1:
        print('Enter a valid Number between 1 and %d' % (num_sections + 1))
        number = int(input('Enter Your Choice: '))

    if number == num_sections + 1:
        return sections
    return [sections[number - 1]]


def execute_command(cmd):
    """
    Creates a process with the given command cmd and writes its output.
    """
    popen = Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdout = b''
    while True:  # Save output to youtube_stdout while this being echoed
        tmp = popen.stdout.read(1)
        stdout += tmp
        print(tmp, end="")
        sys.stdout.flush()
        # do it until the process finish and there isn't output
        if tmp == b"" and popen.poll() is not None:
            break


def main():
    args = parse_args()

    # if no args means we are calling the interactive version
    is_interactive = len(sys.argv) == 1
    if is_interactive:
        args.platform = input('Platform: ')
        args.username = input('Username: ')
        args.password = getpass.getpass()

    change_openedx_site(args.platform)

    if not args.username or not args.password:
        print("You must supply username AND password to log-in")
        sys.exit(2)

    # Prepare Headers
    headers = _edx_get_headers()

    # Login
    resp = edx_login(LOGIN_API, headers, args.username, args.password)
    if not resp.get('success', False):
        print(resp.get('value', "Wrong Email or Password."))
        exit(2)

    courses = get_courses_info(DASHBOARD, headers)
    display_courses(courses)
    selected_course = get_selected_course(courses)

    # Get Available Sections
    courseware_url = selected_course.url.replace('info', 'courseware')
    sections = get_available_sections(courseware_url, headers)

    # Choose Section or choose all
    display_sections(selected_course.name, sections)
    selected_sections = get_selected_sections(sections)

    if is_interactive:
        args.subtitles = input('Download subtitles (y/n)? ').lower() == 'y'

    sections_urls = [selected_section.url for selected_section in selected_sections]
    video_urls, sub_urls = extract_all_subsections(sections_urls, headers)
    if len(video_urls) < 1:
        print('WARNING: No downloadable video found.')
        sys.exit(0)

    if is_interactive:
        # Get Available Video formats
        os.system('youtube-dl -F %s' % video_urls[-1])
        print('Choose a valid format or a set of valid format codes e.g. 22/17/...')
        args.format = input('Choose Format code: ')

    print("[info] Output directory: " + args.output_dir)

    # Download Videos
    video_format_option = args.format + '/mp4' if args.format else 'mp4'
    subtitles_option = '--write-sub' if args.subtitles else ''
    for i, (v, s) in enumerate(zip(video_urls, sub_urls), 1):
        coursename = directory_name(selected_course.name)
        target_dir = os.path.join(args.output_dir, coursename)
        filename_prefix = str(i).zfill(2)
        filename = filename_prefix + "-%(title)s.%(ext)s"
        fullname = os.path.join(target_dir, filename)
        cmd = ['youtube-dl', '-o', fullname, '-f', video_format_option,
               subtitles_option, v]
        # we execute the youtube-dl command to download the videos
        execute_command(cmd)

        if args.subtitles:
            filename = get_filename(target_dir, filename_prefix)
            if filename is None:
                print('[warning] no video downloaded for %s' % filename_prefix)
                continue
            subs_filename = os.path.join(target_dir, filename + '.srt')
            if not os.path.exists(subs_filename):
                subs_string = edx_get_subtitle(s, headers)
                if subs_string:
                    print('[info] Writing edX subtitles: %s' % subs_filename)
                    open(os.path.join(os.getcwd(), subs_filename),
                         'wb+').write(subs_string.encode('utf-8'))


def get_filename(target_dir, filename_prefix):
    """
    Return the basename for the corresponding filename_prefix.
    """
    # This whole function is not the nicest thing, but isolating it makes
    # things clearer. A good refactoring would be to get the info from the
    # video_url or the current output, to avoid the iteration from the
    # current dir.
    filenames = os.listdir(target_dir)
    for name in filenames:  # Find the filename of the downloaded video
        if name.startswith(filename_prefix):
            (basename, ext) = os.path.splitext(name)
            return basename
    return None


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCTRL-C detected, shutting down....")
        sys.exit(0)
