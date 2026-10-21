# basic observation

The recent refactoring subplan introduces the concept of abstract interfaces for various aspects: data-retrieval, data-access, and services.


# vision and goal

The latter makes me realize that the current available system we have in place for the automated cron-jobs should be decoupled from the simulations and be available for generic use in other services (eg also produce the swim-profile and beach-house profiles on a regular basis)



# distant dream

Actually, right around the corner of this work there is the logical extension to arrive at stream-lining the (various) modes of 'reqeusting' (setup of new jobs) and 'delivering' (its results).

Some wild ideas:
- requesting a job-schedule via
    - email
    - form (googleforms?  websiteform?)
    - whatsapp-chat-hook
    - github issue
    - ...
- delivering the results via
    - email
    - website
    - whatsapp-chat-hook
    - ...