
# only import stdlib at the top level. Do not import anything from our
# dependency set, or parts of petmail that require things from the dependency
# set, until runtime, inside a command that specifically needs it.

import os, sys, pprint

try:
    # do not import anything from Twisted that requires the reactor, to allow
    # 'petmail start' to choose a reactor itself
    from twisted.python import usage
except ImportError:
    print >>sys.stderr, "Unable to import Twisted."
    print >>sys.stderr, "Please run 'python setup.py build_deps'"
    raise
    sys.exit(1)

class NoNodeError(Exception):
    def __init__(self, basedir):
        self.basedir = basedir
    def __str__(self):
        return "NoNodeError: '%s' doesn't look like a Petmail basedir, quitting" % self.basedir

class BasedirParameterMixin:
    optParameters = [
        ("basedir", "d", None, "Base directory"),
        ]
    def postOptions(self):
        if not self["basedir"]:
            if self.parent:
                self["basedir"] = self.parent["basedir"]

class BasedirArgument:
    def parseArgs(self, basedir=None):
        if basedir is not None:
            self["basedir"] = basedir

class StartArguments(BasedirArgument):
    def parseArgs(self, basedir=None, *twistd_args):
        # this can't handle e.g. 'petmail start --nodaemon', since then
        # --nodaemon looks like a basedir. Consider using (self, *all_args)
        # and searching for "--" to indicate the start of the twistd_args
        self.twistd_args = twistd_args
        BasedirArgument.parseArgs(self, basedir)

class CreateNodeOptions(BasedirParameterMixin, BasedirArgument, usage.Options):
    optParameters = [
        ("webport", "p", "tcp:0:interface=127.0.0.1",
         "TCP port for the node's HTTP interface."),
        ("webhost", "h", "localhost",
         "hostname/IP-addr to advertise in URLs"),
        ("relay", "r", "tcp:host=localhost:port=5773", "Relay location"),
        ]

class StartNodeOptions(BasedirParameterMixin, StartArguments, usage.Options):
    optFlags = [
        ("no-open", "n", "Do not automatically open the control panel"),
        ]
class StopNodeOptions(BasedirParameterMixin, BasedirArgument, usage.Options):
    pass
class RestartNodeOptions(BasedirParameterMixin, StartArguments, usage.Options):
    def postOptions(self):
        BasedirParameterMixin.postOptions(self)
        self["no-open"] = False
class OpenOptions(BasedirParameterMixin, BasedirArgument, usage.Options):
    optFlags = [
        ("no-open", "n", "Don't open webbrowser, just show URL"),
        ]

class SampleOptions(BasedirParameterMixin, usage.Options):
    optFlags = [
        ("success-object", "o", "Return a success object, not success string"),
        ("error", "e", "Cause a command error (400)"),
        ("server-error", "s", "Cause a server error (500)"),
        ]
    def parseArgs(self, data="no data"):
        self["data"] = data

class InviteOptions(BasedirParameterMixin, usage.Options):
    optParameters = [
        ("petname", "n", None, "Petname for the person being invited"),
        ]
    def parseArgs(self, code):
        self["code"] = code

class AddressbookOptions(BasedirParameterMixin, usage.Options):
    pass

class AddMailboxOptions(BasedirParameterMixin, usage.Options):
    def parseArgs(self, descriptor):
        self["descriptor"] = descriptor

class EnableLocalMailboxOptions(BasedirParameterMixin, usage.Options):
    pass

class SendBasicOptions(BasedirParameterMixin, usage.Options):
    def parseArgs(self, cid, message):
        self["cid"] = cid
        self["message"] = message

class FetchMessagesOptions(BasedirParameterMixin, usage.Options):
    pass

class TestOptions(usage.Options):
    def parseArgs(self, *test_args):
        if not test_args:
            self.test_args = ["petmail"]
        else:
            self.test_args = list(test_args)

class Options(usage.Options):
    synopsis = "\nUsage: petmail <command>"
    optParameters = [
        ("basedir", "d", os.path.expanduser("~/.petmail"), "Base directory"),
        ]
    subCommands = [("create-node", None, CreateNodeOptions, "Create a node"),
                   ("start", None, StartNodeOptions, "Start a node"),
                   ("stop", None, StopNodeOptions, "Stop a node"),
                   ("restart", None, RestartNodeOptions, "Restart a node"),
                   ("open", None, OpenOptions, "Open web control panel"),

                   ("sample", None, SampleOptions, "Sample Command"),
                   ("invite", None, InviteOptions, "Start an Invitation"),
                   ("addressbook", None, AddressbookOptions, "List Addressbook"),
                   ("add-mailbox", None, AddMailboxOptions, "Add a new mailbox"),
                   ("enable-local-mailbox", None, EnableLocalMailboxOptions, "Enable the local (in-process) HTTP mailbox"),
                   ("send-basic", None, SendBasicOptions, "Send a basic message"),
                   ("fetch-messages", None, FetchMessagesOptions, "Fetch all stored messages"),

                   ("test", None, TestOptions, "Run unit tests"),
                   ]

    def opt_version(self):
        """Display version information"""
        from .. import __version__
        print "Petmail version: %s" % __version__
        import twisted.copyright
        print "Twisted version: %s" % twisted.copyright.version
        sys.exit(0)

    def opt_full_version(self):
        """Display detailed version information"""
        from .._version import get_versions
        v = get_versions()
        print "Petmail version: %s (%s)" % (v["version"], v["full"])
        import twisted.copyright
        print "Twisted version: %s" % twisted.copyright.version
        sys.exit(0)

    def getUsage(self, **kwargs):
        t = usage.Options.getUsage(self, **kwargs)
        return t + "\nPlease run 'petmail <command> --help' for more details on each command.\n"

    def postOptions(self):
        if not hasattr(self, 'subOptions'):
            raise usage.UsageError("must specify a command")

def create_node(*args):
    from .create_node import create_node
    return create_node(*args)

def start(*args):
    from .startstop import start
    return start(*args)

def stop(*args):
    from .startstop import stop
    return stop(*args)

def restart(*args):
    from .startstop import restart
    return restart(*args)

def open_control_panel(*args):
    from .open import open_control_panel
    return open_control_panel(*args)


def create_relay(*args):
    from .create_node import create_relay
    return create_relay(*args)

petmail_executable = []

def test(so, stdout, stderr):
    petmail = os.path.abspath(sys.argv[0])
    petmail_executable.append(petmail) # to run bin/petmail in a subprocess
    from twisted.scripts import trial as twisted_trial
    sys.argv = ["trial"] + so.test_args
    twisted_trial.run() # this does not return
    sys.exit(0) # just in case

def render_text(result):
    return result["ok"]+"\n"
def render_all(result):
    return pprint.pformat(result)
def render_addressbook(result):
    lines = []
    for entry in sorted(result["addressbook"], key=lambda e: e["petname"]):
        lines.append('"%s" (%s):' % (entry["petname"], entry["cid"]))
        lines.append(" %s" % {False: "not acknowledged",
                              True: "acknowledged"}[entry["acked"]])
        lines.append(" their verfkey: %s" % entry["their_verfkey"])
        lines.append(" (our verfkey): %s" % entry["my_verfkey"])
    return "\n".join(lines)+"\n"

def render_messages(result):
    lines = []
    for entry in sorted(result["messages"], key=lambda e: e["id"]):
        lines.append('== %d: from %s (cid=%d #%d):' % (
            entry["id"], entry["petname"], entry["cid"], entry["seqnum"]))
        lines.append(str(entry["payload"]))
    return "\n".join(lines)+"\n"

def WebCommand(name, argnames, render=render_text):
    # Build a dispatch function for simple commands that deliver some string
    # arguments to a web API, then display a result.
    def _command(so, out, err):
        from .webwait import command
        args = dict([(argname, so[argname]) for argname in argnames])
        ok, result = command(so["basedir"], name, args, err)
        if ok:
            print >>out, render(result),
            return 0
        else:
            print >>err, result["err"],
            return 1
    return _command

def accept(*args):
    from .accept_invitation import accept_invitation
    return accept_invitation(*args)

DISPATCH = {"create-node": create_node,
            "start": start,
            "stop": stop,
            "restart": restart,
            "open": open_control_panel,
            "create-relay": create_relay,
            "test": test,

            "sample": WebCommand("sample", ["data", "success-object",
                                            "error", "server-error"]),
            "invite": WebCommand("invite", ["petname", "code"]),
            "addressbook": WebCommand("list-addressbook", [],
                                      render=render_addressbook),
            "add-mailbox": WebCommand("add-mailbox", ["descriptor"]),
            "enable-local-mailbox": WebCommand("enable-local-mailbox", []),
            "send-basic": WebCommand("send-basic", ["cid", "message"]),
            "fetch-messages": WebCommand("fetch-messages", [],
                                         render=render_messages),
            "accept": accept,
            }

def run(args, stdout, stderr):
    config = Options()
    try:
        config.parseOptions(args)
    except usage.error, e:
        c = config
        while hasattr(c, 'subOptions'):
            c = c.subOptions
        print >>stderr, str(c)
        print >>stderr, e.args[0]
        return 1
    command = config.subCommand
    so = config.subOptions
    try:
        rc = DISPATCH[command](so, stdout, stderr)
        return rc
    except ImportError, e:
        print >>stderr, "--- ImportError ---"
        print >>stderr, e
        print >>stderr, "Please run 'python setup.py build'"
        raise
        return 1
    except NoNodeError, e:
        print >>stderr, e
        return 1
