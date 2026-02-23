# Copyright 2024 ByteDance and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os
from typing import Any

import torch
from torch.utils.cpp_extension import load

_DESIRED_ARCHS = [
    # (torch_arch_list_entry, gencode_number, min_cuda_version)
    ("7.0", "70", (10, 0)),
    ("8.0", "80", (11, 0)),
    ("8.6", "86", (11, 1)),
    ("9.0", "90", (12, 0)),
    ("12.0", "120", (12, 8)),
]


def _get_cuda_archs() -> tuple[str, list[str]]:
    """Build CUDA arch list and gencode flags filtered by toolkit version."""
    cuda_ver = None
    try:
        ver_str = torch.version.cuda
        if ver_str:
            major, minor = ver_str.split(".")[:2]
            cuda_ver = (int(major), int(minor))
    except Exception:
        pass

    if cuda_ver is None:
        return "7.0;8.0", [
            "-gencode",
            "arch=compute_70,code=sm_70",
            "-gencode",
            "arch=compute_80,code=sm_80",
        ]

    arch_list: list[str] = []
    gencode_flags: list[str] = []
    for arch_str, arch_num, min_ver in _DESIRED_ARCHS:
        if cuda_ver >= min_ver:
            arch_list.append(arch_str)
            gencode_flags.extend(
                ["-gencode", f"arch=compute_{arch_num},code=sm_{arch_num}"]
            )

    if not arch_list:
        arch_list.append("8.0")
        gencode_flags.extend(["-gencode", "arch=compute_80,code=sm_80"])

    return ";".join(arch_list), gencode_flags


def compile(
    name: str, sources: list[str], extra_include_paths: list[str], build_directory: str
) -> Any:
    arch_list, gencode_flags = _get_cuda_archs()
    os.environ["TORCH_CUDA_ARCH_LIST"] = arch_list
    return load(
        name=name,
        sources=sources,
        extra_include_paths=extra_include_paths,
        extra_cflags=[
            "-O3",
            "-DVERSION_GE_1_1",
            "-DVERSION_GE_1_3",
            "-DVERSION_GE_1_5",
        ],
        extra_cuda_cflags=[
            "-O3",
            "--use_fast_math",
            "-DVERSION_GE_1_1",
            "-DVERSION_GE_1_3",
            "-DVERSION_GE_1_5",
            "-std=c++17",
            "-maxrregcount=32",
            "-U__CUDA_NO_HALF_OPERATORS__",
            "-U__CUDA_NO_HALF_CONVERSIONS__",
            "--expt-relaxed-constexpr",
            "--expt-extended-lambda",
            *gencode_flags,
        ],
        verbose=True,
        build_directory=build_directory,
    )
