# Student Status
Every student that's tracked in the FRCAttend system has a status. The status
indicates whether the student is a prospective, current, or a former member.
FrcAttend keeps a history of status changes, so there is typically more than
one status record per student. Statuses are stored in the database's *statuses*
table.

A status consists of several fields.
* student_id: The student that the status record applies to.
* stage: Describes the student's status.
* start_date: the date on which this status became effective.
* reason: An optional reason for the change in status.
* notes: Optional data that explains the status.

## Stage

The possible stages are:
* prospect: A new student who has commenced fall training.
  former_prospect: Student who did not complete fall training or chose not to
  join the team.
* member: Completed membership requirements and joined the team for build
  season.
* former_member: Former member with limited participation (e.g., never
  lettered, just one year).
* alumni: Former member with significant participation (had a role,
  lettered, etc.)

## Reason

The possible reasons are:
* choice: Student chose to leave team.
* graduated: Left team due to graduating from high school.
* incomplete: Student did not satisfactorily complete fall training.
* transferred: Student transferred to a different high school.

The valid reason vary by stage.
* prospect, member: the reason field should be empty.
* former_prospect: choice, incomplete, transferred
* former_member: choice, graduated, transferred.

## Possible Sequences
A typical student will proceed through at least two stages. Here are the
possible sequences of stages.

Student attended a few meetings in fall but decided not to join team.
1. prospect
2. former_prospect (reason=choice)

Student attended a few meetings in fall, applied to join the team, but failed
to complete all membership requirements.
1. prospect
2. former_prospect (reason=incomplete)

New student started attending meetings in the fall, completed all membership
requirements, formally joined the team, but left the team by choice after one
season, with limited participation.
1. prospect
2. member
3. former_member (reason=choice)

New student started attending meetings in the fall, completed all membership
requirements, formally joined the team, and remained on team through their
senior year, until graduation.
1. prospect
2. member
3. alumni (reason=graduated)



1. 


