from typing import IO

from xdsl.dialects.builtin import ModuleOp
from xdsl.xdsl_opt_main import xDSLOptMain

from xdsl_ccpp.dialects.ccpp import CCPP
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.cpp_interop import CPPInteropCap
from xdsl_ccpp.transforms.fir_to_meta import FIRToMeta
from xdsl_ccpp.transforms.generate_kinds import GenerateKinds
from xdsl_ccpp.transforms.lower_ccpp_utils import LowerCCPPUtils
from xdsl_ccpp.transforms.strip_ccpp import StripCCPP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP
from xdsl_ccpp.transforms.suite_kinds import MetaKind
from xdsl_ccpp.transforms.suite_meta import MetaCAP
from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
from xdsl_ccpp.transforms.gpu_debug_print_pass import GPUDebugPrintPass
from xdsl_ccpp.transforms.host_var_match_pass import HostVariableMatchPass
from xdsl_ccpp.transforms.gpu_ccpp_cap_pass import GPUCcppCapPass
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass

class CCPPOptMain(xDSLOptMain):
    def register_all_passes(self):
        super().register_all_passes()
        self.register_pass("generate-suite-cap", lambda: SuiteCAP)
        self.register_pass("generate-ccpp-cap", lambda: CCPPCAP)
        self.register_pass("generate-cpp-cap", lambda: CPPInteropCap)
        self.register_pass("generate-meta-cap", lambda: MetaCAP)
        self.register_pass("generate-meta-kinds", lambda: MetaKind)
        self.register_pass("generate-kinds", lambda: GenerateKinds)
        self.register_pass("strip-ccpp", lambda: StripCCPP)
        self.register_pass("lower-ccpp-utils", lambda: LowerCCPPUtils)
        self.register_pass("fir-to-meta", lambda: FIRToMeta)
        self.register_pass("generate-gpu-data", lambda: GPUDataPass)
        self.register_pass("generate-gpu-debug-prints", lambda: GPUDebugPrintPass)
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
    CCPPOptMain().run()


if __name__ == "__main__":
    main()
