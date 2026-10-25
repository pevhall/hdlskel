#pragma once

#include <stdexcept>
#include <string>

namespace hdlskel::skmap {

// Mirrors the log level selection of setup_logger() in
// pip/skmap/src/skmap/cli_utils.py:
//   default : ERROR and WARNING
//   -v      : also INFO
//   -vv     : also DEBUG
enum class LogVerbosity {
    error = 0,
    info  = 1,
    debug = 2,
};

void set_log_verbosity(LogVerbosity verbosity);
LogVerbosity log_verbosity();

// Write "PREFIX: message" to stderr when `verbosity` is enabled.
void log_msg(LogVerbosity verbosity, const std::string & prefix, const std::string & message);

inline void log_error(const std::string & message) { log_msg(LogVerbosity::error, "ERROR", message); }
// python's default log level is WARNING, so warnings are always shown
inline void log_warning(const std::string & message) { log_msg(LogVerbosity::error, "WARNING", message); }
inline void log_info(const std::string & message)  { log_msg(LogVerbosity::info, "INFO", message); }
inline void log_debug(const std::string & message) { log_msg(LogVerbosity::debug, "DEBUG", message); }

}
