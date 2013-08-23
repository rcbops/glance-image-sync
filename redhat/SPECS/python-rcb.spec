Name:		python-rcb
Version:	0.1.0
Release:	1%{?dist}
Summary:	RCB OpenStack python tools

Group:		Applications/System
License:	Apache License, Version 2.0
URL:		https://github.com/rcbops/glance-image-sync
Source0:	python-rcb-0.1.0.tar.gz
Source1:	openstack-glance-image-sync.init
BuildRoot:	%(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)

BuildArch:	noarch
BuildRequires:	python-setuptools
Requires:	python-glance
Requires:	python-oslo-config

%description
RCB OpenStack python tools for private cloud installations.


%prep
%setup -q


%build
CFLAGS="$RPM_OPT_FLAGS" %{__python} setup.py build


%install
rm -rf %{buildroot}
#make install DESTDIR=%{buildroot}
CFLAGS="$RPM_OPT_FLAGS" %{__python} setup.py install --skip-build --root $RPM_BUILD_ROOT
mkdir -p $RPM_BUILD_ROOT/etc/init.d
install -m 755 $RPM_SOURCE_DIR/openstack-glance-image-sync.init $RPM_BUILD_ROOT/etc/init.d/openstack-glance-image-sync


%clean
rm -rf %{buildroot}


%post
chkconfig --add openstack-glance-image-sync


%files
%defattr(-,root,root,-)
/usr/bin/glance-image-sync
%{python_sitelib}/rcb/
%{python_sitelib}/rcb-0.1.0-py2.6.egg-info/
/etc/init.d/openstack-glance-image-sync
%doc



%changelog
* Wed Aug 07 2013 Matt Thompson (mattt@defunct.ca) - 0.1.0
- Initial build
