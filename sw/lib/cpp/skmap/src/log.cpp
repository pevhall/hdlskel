#include "hdlskel/skmap/log.hpp"

#include <iostream>

namespace hdlskel::skmap {

static LogVerbosity g_log_verbosity = LogVerbosity::error;

void set_log_verbosity(LogVerbosity verbosity) {
    g_log_verbosity = verbosity;
}

LogVerbosity log_verbosity() {
    return g_log_verbosity;
}

void log_msg(LogVerbosity verbosity, const std::string & prefix, const std::string & message) {
    if (verbosity > g_log_verbosity) {
        return;
    }
    std::cerr << prefix << ": " << message << std::endl;
}

}
