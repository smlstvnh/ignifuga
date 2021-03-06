#Copyright (c) 2010-2012, Gabriel Jacobo
#All rights reserved.
#Permission to use this file is granted under the conditions of the Ignifuga Game Engine License
#whose terms are available in the LICENSE file or at http://www.ignifuga.org/license

# Schafer Module: Build Python for Win32 with mingw-w64
# Author: Gabriel Jacobo <gabriel@mdqinc.com>



import os, shlex, shutil
from os.path import *
from subprocess import Popen, PIPE
from ..log import log, error
from schafer import prepare_source, make_python_freeze, SED_CMD, HOSTPYTHON, HOSTPGEN, PATCHES_DIR
from ..util import get_sdl_flags, get_freetype_flags, get_png_flags
import multiprocessing

def prepare(env, target, options, ignifuga_src, python_build):
    # Patch some problems with cross compilation
    cmd = 'patch -p0 -i %s -d %s' % (join(PATCHES_DIR, 'python.mingw32.diff'), python_build)
    Popen(shlex.split(cmd)).communicate()
    cmd = SED_CMD + '"s|Windows.h|windows.h|g" %s' % (join(target.builds.PYTHON, 'Modules', 'signalmodule.c'),)
    Popen(shlex.split(cmd), cwd = target.builds.PYTHON ).communicate()

    # Copy some additional files in the right place
    shutil.copy(join(target.builds.PYTHON, 'PC', 'import_nt.c'), join(target.builds.PYTHON, 'Python', 'import_nt.c'))
    shutil.copy(join(target.builds.PYTHON, 'PC', 'dl_nt.c'), join(target.builds.PYTHON, 'Python', 'dl_nt.c'))
    shutil.copy(join(target.builds.PYTHON, 'PC', 'getpathp.c'), join(target.builds.PYTHON, 'Python', 'getpathp.c'))
    shutil.copy(join(target.builds.PYTHON, 'PC', 'errmap.h'), join(target.builds.PYTHON, 'Objects', 'errmap.h'))

    if options.bare:
        if options.baresrc is None:
            ignifuga_module = ''
        else:
            ignifuga_module = "\%s %s -I%s -I%s -lws2_32 -lwsock32 %s\n" % (options.modulename, ' '.join(ignifuga_src), target.builds.IGNIFUGA, join(target.builds.PYTHON, 'Include'), options.baredependencies if options.baredependencies is not None else '')
    else:
        # Get some required flags
        sdlflags = get_sdl_flags(target).replace('-mwindows', '').replace('-Dmain=SDL_main', '')
        freetypeflags = get_freetype_flags(target)
        ignifuga_module = "\n%s %s -I%s -I%s -lturbojpeg -lSDL2_ttf -lSDL2_image -lSDL2_mixer -lvorbisfile -lvorbis -logg %s %s -lpng12 -ljpeg -lz -lws2_32 -lwsock32 -lstdc++ -lgcc\n" % (options.modulename, ' '.join(ignifuga_src), target.builds.IGNIFUGA, join(target.builds.PYTHON, 'Include'), sdlflags, freetypeflags)

    return ignifuga_module


def make(env, target, options, freeze_modules, frozen_file):
    if not isfile(join(target.builds.PYTHON, 'pyconfig.h')) or not isfile(join(target.builds.PYTHON, 'Makefile')):
        # Linux is built in almost static mode (minus libdl/pthread which make OpenGL fail if compiled statically)
        if options.bare:
            sdlldflags = sdlcflags = ''
        else:
            cmd = join(target.dist, 'bin', 'sdl2-config' ) + ' --static-libs'
            sdlldflags = Popen(shlex.split(cmd), stdout=PIPE, env=env).communicate()[0].split('\n')[0].replace('-lpthread', '').replace('-ldl', '') # Removing pthread and dl to make them dynamically bound (req'd for Linux)
            cmd = join(target.dist, 'bin', 'sdl2-config' ) + ' --cflags'
            sdlcflags = Popen(shlex.split(cmd), stdout=PIPE, env=env).communicate()[0].split('\n')[0]
        extralibs = "-lodbc32 -lwinspool -lwinmm -lshell32 -lcomctl32 -lodbc32 -ladvapi32 -lopengl32 -lglu32 -lole32 -loleaut32 -luuid"
        cmd = 'rm -f configure'
        Popen(shlex.split(cmd), cwd = target.builds.PYTHON, env=env).communicate()
        cmd = 'autoconf'
        Popen(shlex.split(cmd), cwd = target.builds.PYTHON, env=env).communicate()
        # -DSTATIC_LIB is used for compiling libRocket as fully static under mingw
        cmd = './configure --enable-silent-rules ABI="longlong" LDFLAGS="%s -Wl,--no-export-dynamic -static-libgcc -static %s %s" LDLAST="-lws2_32 -lwsock32" CFLAGS="%s -DBOOST_PYTHON_STATIC_LIB -DBOOST_PYTHON_SOURCE -DSTATIC_LIB -D__MINGW32__ -DMS_WIN64 -DMS_WINDOWS -DHAVE_USABLE_WCHAR_T" CPPFLAGS="-DBOOST_PYTHON_STATIC_LIB -DBOOST_PYTHON_SOURCE -DSTATIC_LIB -static %s" LINKFORSHARED=" " LIBOBJS="import_nt.o dl_nt.o getpathp.o" THREADOBJ="Python/thread.o" DYNLOADFILE="dynload_win.o" --disable-shared HOSTPYTHON=%s HOSTPGEN=%s --host=x86_64-w64-mingw32 --build=i686-pc-linux-gnu  --prefix="%s"'% (env['LDFLAGS'], sdlldflags, extralibs, env['CFLAGS'], sdlcflags, HOSTPYTHON, HOSTPGEN, target.dist,)
        if options.valgrind:
            cmd += ' --with-valgrind'
        Popen(shlex.split(cmd), cwd = target.builds.PYTHON, env=env).communicate()

        cmd = SED_CMD + '"s|\${LIBOBJDIR}fileblocks\$U\.o||g" %s' % (join(target.builds.PYTHON, 'Makefile'))
        Popen(shlex.split(cmd), cwd = target.builds.PYTHON).communicate()
        # Enable NT Threads
        cmd = SED_CMD + '"s|.*NT_THREADS.*|#define NT_THREADS|g" %s' % (join(target.builds.PYTHON, 'pyconfig.h'))
        Popen(shlex.split(cmd), cwd = target.builds.PYTHON).communicate()

        # Disable PTY stuff that gets activated because of errors in the configure script
        cmd = SED_CMD + '"s|.*HAVE_OPENPTY.*|#undef HAVE_OPENPTY|g" %s' % (join(target.builds.PYTHON, 'pyconfig.h'))
        Popen(shlex.split(cmd), cwd = target.builds.PYTHON).communicate()
        cmd = SED_CMD + '"s|.*HAVE__GETPTY.*|#undef HAVE__GETPTY|g" %s' % (join(target.builds.PYTHON, 'pyconfig.h'))
        Popen(shlex.split(cmd), cwd = target.builds.PYTHON).communicate()
        cmd = SED_CMD + '"s|.*HAVE_DEV_PTMX.*|#undef HAVE_DEV_PTMX|g" %s' % (join(target.builds.PYTHON, 'pyconfig.h'))
        Popen(shlex.split(cmd), cwd = target.builds.PYTHON).communicate()

        # Mingw64 defines pid_t as long long (8 bytes), while Python requires that sizeof(pid_t)<sizeof(long) ( and long  for Windows is 4 bytes).
        # So, we need to override the typedef'ing done for pid_t and set it to int and a size of 4 bytes
        # This does not have major repercusions because the Python code for threads doesn't use this typedef at all AFAICT
        cmd = SED_CMD + '"s|^/\* #undef pid_t.*|#undef pid_t\\n#define pid_t int|g" %s' % (join(target.builds.PYTHON, 'pyconfig.h'))
        Popen(shlex.split(cmd), cwd = target.builds.PYTHON).communicate()
        cmd = SED_CMD + '"s|^#define SIZEOF_PID_T 8|#define SIZEOF_PID_T 4|g" %s' % (join(target.builds.PYTHON, 'pyconfig.h'))
        Popen(shlex.split(cmd), cwd = target.builds.PYTHON).communicate()

    freeze_modules += ['ntpath', 'locale']
    make_python_freeze(options.platform, freeze_modules, frozen_file)
    if isfile(join(target.dist, 'lib', 'libpython2.7.a')):
        os.remove(join(target.dist, 'lib', 'libpython2.7.a'))

    cmd = 'make V=0 install -k -j%d HOSTPYTHON=%s HOSTPGEN=%s CROSS_COMPILE=mingw32msvc CROSS_COMPILE_TARGET=yes'  % (multiprocessing.cpu_count(), HOSTPYTHON, HOSTPGEN)
    Popen(shlex.split(cmd), cwd = target.builds.PYTHON, env=env).communicate()

    if not isdir (join(target.dist, 'include', 'Modules')):
        os.makedirs(join(target.dist, 'include', 'Modules'))
    shutil.copy(join(target.builds.PYTHON, 'Modules/greenlet.h'), join(target.dist, 'include', 'Modules', 'greenlet.h'))

    # Check success
    if isfile(join(target.dist, 'lib', 'libpython2.7.a')):
        log('Python built successfully')
    else:
        error('Error building python')

    return True