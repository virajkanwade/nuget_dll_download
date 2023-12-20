# nuget_dll_download
nuget package dll downloader for use with pythonnet

While working with pythonnet, realized that it does not raise any error if any dependency is missing for the .NET DLL you are using.

The only way to download all dependencies properly is to use `dotnet` or `nuget` commands. The problem is, both require creating a .NET project for it to work. Creating a project just for downloading DLLs didn't make sense.

So using the nuget API (https://learn.microsoft.com/en-us/nuget/api/registration-base-url-resource), I decided to write this helper script to download all dependency DLLs without having to create a .NET project.

## Setup
`pip install -r requirements.txt`

## Running
`python nuget_dll_download.py Hl7.Fhir.R4 5.4.0`

## Output
The DLLs will be stored to `downloads/Hl7.Fhir.R4/5.4.0` in the current folder.
