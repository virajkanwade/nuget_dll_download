import os
import shutil
import sys
import tempfile
from zipfile import ZipFile

import requests
from packaging.version import Version

SERVICE_INDEX_URL = "https://api.nuget.org/v3/index.json"


def get_registrations_base_url() -> str:
    response: dict = requests.get(SERVICE_INDEX_URL).json()
    return [r for r in response["resources"] if r["@type"] == "RegistrationsBaseUrl"][0]["@id"]


def get_package_version_in_range(item: dict, package_version_range: str) -> str:
    # https://learn.microsoft.com/en-us/nuget/concepts/package-versioning#version-ranges
    arr = [r.strip() for r in package_version_range.split(",")]

    if len(arr) == 1:
        if arr[0][0] != "[" and arr[0][0] != "(":
            arr[0] = "[" + arr[0]
            arr.append(")")
        elif arr[0][0] == "[" and arr[0][-1] == "]":
            return arr[0][1:-1]
        elif arr[0] == "":
            return item["upper"]

    min_inclusive = True if arr[0][0] == "[" else False
    max_inclusive = True if arr[1][-1] == "]" else False

    min_version = None if not arr[0][1:] else Version(arr[0][1:])
    max_version = None if not arr[1][:-1] else Version(arr[1][:-1])

    package_version_str = None
    package_version = None

    for _item in item["items"]:
        catalog_entry = _item["catalogEntry"]
        version_str = catalog_entry["version"]
        version = Version(version_str)

        min_match = False
        max_match = False

        if min_version is not None and (
            (min_inclusive and version >= min_version) or (not min_inclusive and version > min_version)
        ):
            min_match = True

        if max_version is not None and (
            (max_inclusive and version <= max_version) or (not max_inclusive and version < max_version)
        ):
            max_match = True

        if (
            ((min_version is not None and min_match) and (max_version is not None and max_match))
            or ((min_version is not None and min_match) and (max_version is None))
            or ((min_version is None) and (max_version is not None and max_match))
        ) and (package_version is None or package_version < version):
            package_version = version
            package_version_str = version_str

    return package_version_str


def get_package_metadata(
    registrations_base_url: str,
    package_id: str,
    package_version: str | None = None,
    package_version_range: str | None = None,
) -> tuple:
    response = requests.get(f"{registrations_base_url}{package_id.lower()}/index.json").json()

    _version_str = None
    _version = None

    for item in response["items"]:
        if _version_str is None:
            if package_version_range is None:
                _version_str = item["upper"]
            else:
                _version_str = get_package_version_in_range(item, package_version_range)

        if _version_str is not None:
            _v = Version(_version_str)
            if _version is None or _version < _v:
                _version = _v

    package_version = _version_str

    print(package_id, package_version, "count: ", response["count"])

    for item in response["items"]:
        for _item in item["items"]:
            catalog_entry = _item["catalogEntry"]
            if catalog_entry["version"] == package_version:
                return catalog_entry, package_version

    return None, None


def download_nupkg(nupkg_url: str, nupkg_file: str) -> None:
    response = requests.get(nupkg_url, stream=True)
    with open(nupkg_file, mode="wb") as fp:
        for chunk in response.iter_content(chunk_size=10 * 1024):
            fp.write(chunk)


def extract_dll_from_nupkg(nupkg_file: str, nupkg_extract_path: str, download_dir: str) -> None:
    with ZipFile(nupkg_file) as myzip:
        myzip.extractall(nupkg_extract_path)

    lib_path = os.path.join(nupkg_extract_path, "lib")

    root_path = None
    _root_path = os.path.join(lib_path, "net6.0")
    if os.path.isdir(_root_path):
        root_path = _root_path

    # if root_path is None:
    #     _root_path = os.path.join(lib_path, "net5.0")
    #     if os.path.isdir(_root_path):
    #         root_path = _root_path

    if root_path is None:
        print("ERROR")
        for root, dirs, files in os.walk(lib_path):
            if root == lib_path and len(dirs) == 1:
                print(dirs)
                root_path = os.path.join(root, dirs[0])

    if root_path is not None:
        for root, _, files in os.walk(root_path):
            for filename in files:
                if filename.endswith(".dll"):
                    shutil.copyfile(os.path.join(root, filename), os.path.join(download_dir, filename))


def handle_dependencies(
    registrations_base_url: str, download_dir: str, tmp_dir: str, package_metadata: dict
) -> None:
    dependency_groups = package_metadata["dependencyGroups"]

    for dependency_group in dependency_groups:
        if dependency_group["targetFramework"] == "net6.0":
            for dependency in dependency_group.get("dependencies", []):
                _package_id = dependency["id"]
                if _package_id.startswith("System."):
                    continue
                range = dependency["range"]

                print(_package_id, range)

                get_package(
                    registrations_base_url, download_dir, tmp_dir, _package_id, package_version_range=range
                )


def get_package(
    registrations_base_url: str,
    download_dir: str,
    tmp_dir: str,
    package_id: str,
    package_version: str | None = None,
    package_version_range: str | None = None,
) -> None:
    print("-" * 50)
    package_metadata, package_version = get_package_metadata(
        registrations_base_url, package_id, package_version, package_version_range
    )

    nupkg_file = os.path.join(tmp_dir, f"{package_id.lower()}.{package_version}.nupkg")
    nupkg_extract_path = os.path.join(tmp_dir, package_id, package_version)

    download_nupkg(package_metadata["packageContent"], nupkg_file)
    extract_dll_from_nupkg(nupkg_file, nupkg_extract_path, download_dir)

    handle_dependencies(registrations_base_url, download_dir, tmp_dir, package_metadata)


def main() -> None:
    package_id: str = sys.argv[1]
    package_version: str = sys.argv[2]

    registrations_base_url: str = get_registrations_base_url()

    download_dir = os.path.join(os.path.dirname(__file__), "downloads", package_id, package_version)
    os.makedirs(download_dir, exist_ok=True)

    _tmp_dir = tempfile.TemporaryDirectory()
    tmp_dir = _tmp_dir.name

    get_package(registrations_base_url, download_dir, tmp_dir, package_id, package_version)


if __name__ == "__main__":
    main()
