import argparse
import os
import sys
from typing import IO

from xdsl.dialects.builtin import ModuleOp
from xdsl.passes import ModulePass, PassPipeline
from xdsl.printer import Printer
from xdsl.xdsl_opt_main import xDSLOptMain

from xdsl_ccpp.dialects.ccpp import CCPP
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.cpp_interop import CPPInteropCap
from xdsl_ccpp.transforms.flatten_composites import FlattenComposites
from xdsl_ccpp.transforms.lower_packages import LowerPackages
from xdsl_ccpp.transforms.package_scope import ScopePackages
from xdsl_ccpp.transforms.generate_kinds import GenerateKinds
from xdsl_ccpp.transforms.strip_ccpp import StripCCPP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP
from xdsl_ccpp.transforms.suite_kinds import MetaKind
from xdsl_ccpp.transforms.suite_meta import MetaCAP
from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
from xdsl_ccpp.transforms.gpu_debug_print_pass import GPUDebugPrintPass
from xdsl_ccpp.transforms.host_var_match_pass import HostVariableMatchPass
from xdsl_ccpp.transforms.gpu_ccpp_cap_pass import GPUCcppCapPass
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.scheme_io_capture_pass import SchemeIOCapturePass
from xdsl_ccpp.util.ccpp_conventions import set_verbosity
from xdsl_ccpp.util.errors import report_input_errors

# Set (to anything but "" or "0") to verify the IR after every pass by
# default; the test suite sets it (tests/conftest.py).
VERIFY_EACH_PASS_ENV = "XDSL_CCPP_VERIFY_EACH_PASS"


class CCPPOptMain(xDSLOptMain):
    def register_all_arguments(self, arg_parser: argparse.ArgumentParser):
        super().register_all_arguments(arg_parser)
        arg_parser.add_argument(
            "--verbose",
            type=int,
            choices=[0, 1, 2],
            default=1,
            help="Verbosity: at 2, an error in the input (e.g. a scheme argument "
                 "with no host match) shows its traceback, not only its message. "
                 "Forwarded from ccpp_dsl.py's own --verbose.",
        )
        arg_parser.add_argument(
            "--verify-each-pass",
            action="store_true",
            default=os.environ.get(VERIFY_EACH_PASS_ENV, "") not in ("", "0"),
            help="verify the IR after every pass, not only before and after "
            f"the pipeline (default: on if ${VERIFY_EACH_PASS_ENV} is set)",
        )

    def setup_pipeline(self):
        """xDSLOptMain's pipeline, but verifying between passes only with
        --verify-each-pass: verification after each of the ~10 passes was
        16% of a cam4 generation. The module is still verified before and
        after the pipeline (apply_passes), unless --disable-verify."""

        def callback(
            previous_pass: ModulePass, module: ModuleOp, next_pass: ModulePass
        ) -> None:
            if self.args.verify_each_pass and not self.args.disable_verify:
                module.verify()
            if self.args.print_between_passes:
                print(f"IR after {previous_pass.name}:")
                Printer(stream=sys.stdout).print_op(module)
                print("\n\n\n")

        self.pipeline = PassPipeline.parse_spec(
            self.available_passes, self.args.passes, callback
        )

    def register_all_passes(self):
        super().register_all_passes()
        self.register_pass("scope-packages", lambda: ScopePackages)
        self.register_pass("lower-packages", lambda: LowerPackages)
        self.register_pass("flatten-composites", lambda: FlattenComposites)
        self.register_pass("generate-suite-cap", lambda: SuiteCAP)
        self.register_pass("generate-ccpp-cap", lambda: CCPPCAP)
        self.register_pass("generate-cpp-cap", lambda: CPPInteropCap)
        self.register_pass("generate-meta-cap", lambda: MetaCAP)
        self.register_pass("generate-meta-kinds", lambda: MetaKind)
        self.register_pass("generate-kinds", lambda: GenerateKinds)
        self.register_pass("strip-ccpp", lambda: StripCCPP)
        self.register_pass("generate-gpu-data", lambda: GPUDataPass)
        self.register_pass("generate-gpu-debug-prints", lambda: GPUDebugPrintPass)
        self.register_pass("generate-scheme-io-capture", lambda: SchemeIOCapturePass)
        self.register_pass("generate-host-match", lambda: HostVariableMatchPass)
        self.register_pass("generate-gpu-ccpp-cap", lambda: GPUCcppCapPass)
        self.register_pass("generate-arg-ownership", lambda: ArgOwnershipPass)

    def register_all_targets(self):
        super().register_all_targets()

        def _output_ftn(prog: ModuleOp, output: IO[str]):
            from xdsl_ccpp.backend.print_ftn import print_to_ftn

            print_to_ftn(prog, output)

        def _output_cpp_header(prog: ModuleOp, output: IO[str]):
            from xdsl_ccpp.backend.print_cpp_header import print_to_cpp_headers

            print_to_cpp_headers(prog, output)

        def _output_ftn_and_cpp_header(prog: ModuleOp, output: IO[str]):
            # Combined target: print both from the SAME already-
            # transformed `prog`, one process/pipeline run instead of
            # the two full independent re-parses+re-transforms
            # ccpp_dsl.py used to pay for (cpp-dual-print-pipeline).
            # print_to_ftn/print_to_cpp_headers are each a pure,
            # read-only traversal of `prog` -- safe to call twice on the
            # same module. Neither function knows about the other's
            # output when called back-to-back, so the cpp_header section
            # is buffered first to detect whether it wrote anything
            # (nothing, when there's no BIND(C) content) before deciding
            # whether a "// -----" divider is needed between the two.
            import io

            from xdsl_ccpp.backend.print_cpp_header import print_to_cpp_headers
            from xdsl_ccpp.backend.print_ftn import print_to_ftn

            print_to_ftn(prog, output)
            cpp_buf = io.StringIO()
            print_to_cpp_headers(prog, cpp_buf)
            cpp_text = cpp_buf.getvalue()
            if cpp_text:
                output.write("// -----\n")
                output.write(cpp_text)

        self.available_targets["ftn"] = _output_ftn
        self.available_targets["cpp_header"] = _output_cpp_header
        self.available_targets["ftn_and_cpp_header"] = _output_ftn_and_cpp_header

    def register_all_dialects(self):
        super().register_all_dialects()
        self.ctx.load_dialect(CCPP)
        self.ctx.load_dialect(CCPPUtils)

    def register_all_frontends(self):
        super().register_all_frontends()


def main():
    opt = CCPPOptMain()
    set_verbosity(opt.args.verbose)
    report_input_errors(opt.run)


if __name__ == "__main__":
    main()
